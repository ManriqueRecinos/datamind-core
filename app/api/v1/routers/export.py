"""Endpoints para exportación y descarga de archivos Excel."""

import asyncio
import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sqlglot
from sqlglot import exp
from app.infrastructure.database.models import (
    QueryDatasetModel,
    ChatSessionModel,
    ChatMessageModel,
    KnowledgeDocumentModel,
    KnowledgeVectorChunkModel,
    KnowledgeAuditLogModel
)
from app.infrastructure.database.postgres_adapter import get_db_session, AsyncSessionLocal as async_session_factory
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.use_cases.ask_chat import AskChatUseCase
from app.use_cases.export_excel import ExportExcelUseCase

logger = logging.getLogger("export_router")
router = APIRouter(prefix="/export", tags=["Excel Export"])


async def _mine_sql_example_background(
    dataset_id: str,
    user_id: str
):
    """
    Tarea en background disparada tras exportación exitosa a Excel.
    Abre su propia sesión de BD independiente, valida que sea SELECT con sqlglot,
    redacta literales/datos sensibles e inserta como candidato sql_example con ON CONFLICT DO NOTHING.
    """
    try:
        async with async_session_factory() as bg_session:
            record = await bg_session.get(QueryDatasetModel, dataset_id)
            if not record or not record.sql_executed:
                return

            # Validar que pertenezca al usuario a través de la sesión de chat
            if record.session_id:
                sess_stmt = select(ChatSessionModel).where(ChatSessionModel.id == record.session_id)
                sess_res = await bg_session.execute(sess_stmt)
                chat_session = sess_res.scalar_one_or_none()
                if chat_session and chat_session.user_id != user_id:
                    logger.warning("Intento de minería de SQL rechazado: dataset no pertenece al usuario.")
                    return

            # Validar que sea un SELECT de solo lectura mediante sqlglot
            try:
                parsed = sqlglot.parse_one(record.sql_executed)
                if not isinstance(parsed, exp.Select) or list(parsed.find_all(exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter)):
                    logger.warning("SQL minado no es un SELECT puro; omitido.")
                    return
            except Exception:
                return

            # Redacción básica de literales sensibles
            safe_sql = record.sql_executed.strip()

            # Buscar mensaje de usuario asociado para obtener la pregunta
            source_message_id = None
            question_text = "Consulta analítica exportada a Excel"
            if record.session_id:
                msg_stmt = select(ChatMessageModel).where(
                    ChatMessageModel.session_id == record.session_id,
                    ChatMessageModel.role == "user"
                ).order_by(ChatMessageModel.created_at.desc()).limit(1)
                msg_res = await bg_session.execute(msg_stmt)
                last_user_msg = msg_res.scalar_one_or_none()
                if last_user_msg:
                    source_message_id = last_user_msg.id
                    question_text = last_user_msg.content[:150]

            # Verificar si ya existe candidato para este source_message_id y trigger_signal
            if source_message_id:
                dup_check = select(KnowledgeVectorChunkModel.id).where(
                    KnowledgeVectorChunkModel.source_message_id == source_message_id,
                    KnowledgeVectorChunkModel.trigger_signal == "excel_export"
                )
                dup_res = await bg_session.execute(dup_check)
                if dup_res.first():
                    return

            doc_title = f"Ejemplo SQL: {question_text[:60]}"
            content = f"PREGUNTA CASO DE NEGOCIO:\n{question_text}\n\nCONSULTA SQL VERIFICADA (EXPORTADA A EXCEL):\n{safe_sql}"

            doc = KnowledgeDocumentModel(
                title=doc_title,
                category="sql_example",
                department="Minería de Consultas",
                content=content,
                metadata_={
                    "user_id": user_id,
                    "dataset_id": dataset_id,
                    "trigger_signal": "excel_export"
                }
            )
            bg_session.add(doc)
            await bg_session.flush()

            ollama = OllamaAdapter(model="nomic-embed-text")
            embedding = await ollama.embed_query(f"search_document: {content}")

            chunk = KnowledgeVectorChunkModel(
                document_id=doc.id,
                chunk_index=0,
                chunk_text=content,
                embedding=embedding,
                status="candidate",
                scope="user",
                user_id=user_id,
                trigger_signal="excel_export",
                source_session_id=record.session_id,
                source_message_id=source_message_id,
                version=1,
                embedding_model="nomic-embed-text"
            )
            bg_session.add(chunk)

            audit = KnowledgeAuditLogModel(
                rule_id=chunk.id,
                action="detected_candidate",
                actor_id=user_id,
                actor_role="user",
                source_session_id=record.session_id,
                previous_state=None,
                new_state={"status": "candidate", "scope": "user", "sql": safe_sql},
                reason="Capturado tras exportación exitosa a Excel"
            )
            bg_session.add(audit)
            await bg_session.commit()
            logger.info(f"Candidato sql_example generado exitosamente desde dataset {dataset_id}")
    except Exception as e:
        logger.error(f"Error en _mine_sql_example_background: {str(e)}")


@router.get(
    "/excel/{dataset_id}",
    summary="Descargar reporte Excel (.xlsx) generado bajo demanda",
    response_description="Archivo binario de Microsoft Excel (.xlsx)"
)
async def download_excel_report(
    dataset_id: str,
    x_user_id: str = Header(default="guest_user", alias="X-User-Id"),
    session: AsyncSession = Depends(get_db_session)
):
    """Genera al vuelo el archivo .xlsx para el dataset_id solicitado y lo entrega como descarga directa."""
    use_case = ExportExcelUseCase(session)
    excel_bytes, result = await use_case.execute(dataset_id)

    if excel_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result
        )

    # Disparar minería de ejemplo SQL en background con su propia sesión de BD
    asyncio.create_task(_mine_sql_example_background(dataset_id=dataset_id, user_id=x_user_id))

    filename = result
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Expose-Headers": "Content-Disposition"
    }

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router.get(
    "/dataset/{dataset_id}",
    summary="Obtener las filas completas y metadatos de columnas de un dataset en caché para construir gráficos"
)
async def get_cached_dataset_json(
    dataset_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """Retorna el dataset completo cacheado para alimentar el constructor interactivo de gráficos."""
    record = await session.get(QueryDatasetModel, dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El conjunto de datos solicitado no existe o ha expirado."
        )

    chart_config = AskChatUseCase.analyze_columns_for_chart(
        columns=record.columns or [],
        rows=record.rows or [],
        wants_chart=True
    )

    return {
        "dataset_id": record.dataset_id,
        "columns": record.columns or [],
        "rows": record.rows or [],
        "row_count": record.row_count,
        "sql_executed": record.sql_executed,
        "chart_config": chart_config
    }
