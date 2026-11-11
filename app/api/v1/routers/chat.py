"""Endpoints para la conversación de chat y streaming en tiempo real (SSE)."""

import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSessionDetailSchema,
    ChatSessionSummarySchema,
)
from app.api.v1.streaming import format_sse
from app.infrastructure.database.postgres_adapter import get_db_session, AsyncSessionLocal as async_session_factory
from app.infrastructure.llm.inference_concurrency_manager import InferenceConcurrencyManager
from app.use_cases.ask_chat import AskChatUseCase
from app.use_cases.detect_dialogue_correction import DetectDialogueCorrectionUseCase

router = APIRouter(prefix="/chat", tags=["Chat & Text-to-SQL"])


async def _run_dialogue_detector_background(
    user_id: str,
    session_id: str,
    message_id: str,
    connection_id: Optional[str],
    user_message: str,
    previous_assistant_message: Optional[str],
    previous_sql: Optional[str]
):
    """Ejecuta el detector en background abriendo su propia AsyncSession independiente."""
    try:
        async with async_session_factory() as bg_session:
            use_case = DetectDialogueCorrectionUseCase(bg_session)
            await use_case.execute(
                user_id=user_id,
                session_id=session_id,
                message_id=message_id,
                connection_id=connection_id,
                user_message=user_message,
                previous_assistant_message=previous_assistant_message,
                previous_sql=previous_sql
            )
    except Exception as e:
        import logging
        logging.getLogger("chat_stream").error(f"Error en detector background: {str(e)}")


@router.post(
    "",
    response_model=ChatResponse,
    summary="Enviar mensaje conversacional (Respuesta JSON completa)"
)
async def send_chat_message(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Procesa la pregunta del usuario mediante RAG o Text-to-SQL y retorna la respuesta con metadatos."""
    try:
        use_case = AskChatUseCase(session)
        result = await use_case.execute_sync(
            prompt=payload.prompt,
            session_id=payload.session_id,
            user_id=payload.user_id or "user",
            connection_id=payload.connection_id,
            user_role=payload.user_role or "user",
            user_permissions=payload.user_permissions or [],
            attachment_ids=payload.attachment_ids or []
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en el asistente de chat: {str(e)}"
        )


@router.post(
    "/stream",
    summary="Enviar mensaje conversacional con Streaming en vivo (SSE)"
)
async def stream_chat_message(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Transmite la respuesta token a token usando Server-Sent Events (SSE) con soporte de Heartbeat y Reintento."""
    async def sse_generator():
        use_case = AskChatUseCase(session)
        concurrency_manager = InferenceConcurrencyManager()
        concurrency_manager.register_user_query_start(payload.session_id)

        try:
            # Tarea asíncrona de inferencia y persistencia
            task = asyncio.create_task(
                use_case.execute_sync(
                    prompt=payload.prompt,
                    session_id=payload.session_id,
                    user_id=payload.user_id or "user",
                    connection_id=payload.connection_id,
                    user_role=payload.user_role or "user",
                    user_permissions=payload.user_permissions or [],
                    retry_message_id=payload.retry_message_id,
                    attachment_ids=payload.attachment_ids or []
                )
            )

            # Mientras la inferencia/SQL se procesa, emitir latidos periódicos cada 5 segundos
            while not task.done():
                done, _ = await asyncio.wait([task], timeout=5.0)
                if not done:
                    # Comentario SSE para mantener viva la conexión HTTP y reiniciar timers de inactividad
                    yield ": ping\n\n"

            result = await task

            # Emitir evento oficial de sesión con el session_id real persistido en base de datos
            yield format_sse("session", {
                "status": "processing",
                "session_id": result["session_id"]
            })

            # Si se generó una solicitud de aclaración interactiva (Feature 006)
            if result.get("clarification"):
                yield format_sse("clarification", result["clarification"])

            # Transmitir el mensaje en tokens para la animación
            tokens = result["message"].split(" ")
            for idx, token in enumerate(tokens):
                separator = " " if idx < len(tokens) - 1 else ""
                yield format_sse("token", {"text": token + separator})

            # Si produjo datos tabulares, emitir el evento dataset para habilitar el botón de Excel y Constructor de Gráficos
            if result.get("has_tabular_data") and result.get("dataset_id"):
                yield format_sse("dataset", {
                    "dataset_id": result["dataset_id"],
                    "row_count": result.get("row_count", 0),
                    "columns": result.get("columns", []),
                    "preview_rows": result.get("preview_rows", []),
                    "sql": result.get("generated_sql"),
                    "chart_config": result.get("chart_config")
                })

            # Emitir evento de finalización (aditivo con rules_applied manteniendo session_id y latency_ms)
            done_payload = {
                "session_id": result["session_id"],
                "latency_ms": result["latency_ms"]
            }
            if result.get("rules_applied"):
                done_payload["rules_applied"] = result["rules_applied"]
            else:
                done_payload["rules_applied"] = []

            yield format_sse("done", done_payload)

            # Disparar detector de correcciones en background (no bloquea SSE)
            bg_user_msg_id = result.get("user_message_id")
            if bg_user_msg_id:
                detector_task = asyncio.create_task(
                    _run_dialogue_detector_background(
                        user_id=str(payload.user_id or "user"),
                        session_id=str(result["session_id"]),
                        message_id=str(bg_user_msg_id),
                        connection_id=payload.connection_id,
                        user_message=payload.prompt,
                        previous_assistant_message=result.get("prev_asst_content"),
                        previous_sql=result.get("prev_asst_sql")
                    )
                )
                concurrency_manager.register_background_detector(str(result["session_id"]), detector_task)
                detector_task.add_done_callback(
                    lambda _: concurrency_manager.unregister_background_detector(str(result["session_id"]))
                )
        except Exception as e:
            yield format_sse("error", {"detail": str(e)})
        finally:
            concurrency_manager.register_user_query_end()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get(
    "/sessions",
    response_model=List[ChatSessionSummarySchema],
    summary="Listar historial de sesiones de conversación de un usuario"
)
async def list_chat_sessions(
    user_id: str = Query(default="user", description="Identificador del usuario autenticado"),
    session: AsyncSession = Depends(get_db_session)
):
    """Retorna la lista de sesiones conversacionales del usuario ordenadas por actividad reciente."""
    use_case = AskChatUseCase(session)
    return await use_case.list_user_sessions(user_id=user_id)


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetailSchema,
    summary="Obtener todos los mensajes e historial de una sesión"
)
async def get_chat_session_detail(
    session_id: str,
    user_id: Optional[str] = Query(default=None, description="Identificador del usuario propietario"),
    session: AsyncSession = Depends(get_db_session)
):
    """Recupera la sesión y su secuencia cronológica de mensajes con metadatos de datasets y gráficos."""
    use_case = AskChatUseCase(session)
    detail = await use_case.get_session_detail(session_id=session_id, user_id=user_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la sesión solicitada."
        )
    return detail


@router.delete(
    "/sessions/{session_id}",
    summary="Eliminar una sesión del historial de conversaciones"
)
async def delete_chat_session(
    session_id: str,
    user_id: Optional[str] = Query(default=None, description="Identificador del usuario propietario"),
    session: AsyncSession = Depends(get_db_session)
):
    """Elimina la sesión conversacional y sus mensajes asociados."""
    use_case = AskChatUseCase(session)
    deleted = await use_case.delete_session(session_id=session_id, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la sesión a eliminar."
        )
    return {"deleted": True, "session_id": session_id}
