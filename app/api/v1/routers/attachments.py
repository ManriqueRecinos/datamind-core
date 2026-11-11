"""Endpoints REST para la subida, validación y gestión de archivos adjuntos en el chat."""

import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.attachments import (
    AttachmentUploadResponse,
    AttachmentSummarySchema,
    AttachmentSchemaPreview
)
from app.infrastructure.database.models import ChatAttachmentModel, ChatSessionModel
from app.infrastructure.database.postgres_adapter import get_db_session
from app.infrastructure.security.file_security_validator import FileSecurityValidator
from app.infrastructure.analytics.attachment_analytics_engine import AttachmentAnalyticsEngine

router = APIRouter(prefix="/chat/attachments", tags=["Chat Attachments & Local Analytics"])

BASE_STORAGE_PATH = Path("storage/attachments")


@router.post(
    "",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir y analizar un archivo tabular (CSV, TSV, XLSX) para analítica local"
)
async def upload_chat_attachment(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    user_id: str = Form(default="user"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Recibe un archivo tabular multipart, verifica cuotas (máx 3 por sesión),
    inspecciona magic bytes, ejecuta sandbox DuckDB/Polars y retorna el esquema inferido.
    """
    # 1. Validar que la sesión exista
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id inválido.")

    chat_sess = await session.get(ChatSessionModel, sess_uuid)
    if not chat_sess:
        # Si la sesión aún no existe en BD, crearla automáticamente para el usuario
        chat_sess = ChatSessionModel(
            id=sess_uuid,
            user_id=user_id,
            title="Conversación con archivos"
        )
        session.add(chat_sess)
        await session.flush()

    # 2. Validar cuota: máximo 3 archivos adjuntos por sesión
    count_stmt = select(func.count(ChatAttachmentModel.id)).where(
        ChatAttachmentModel.session_id == sess_uuid
    )
    existing_count = (await session.execute(count_stmt)).scalar() or 0
    if existing_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Límite alcanzado: máximo 3 archivos adjuntos por sesión."
        )

    # 3. Leer cabecera para validación de tipo MIME real por magic bytes
    header_bytes = await file.read(512)
    await file.seek(0)

    original_filename = file.filename or "archivo_datos.csv"
    real_mime = FileSecurityValidator.detect_real_mime(header_bytes, original_filename)

    # 4. Guardar archivo temporal en disco de forma segura
    session_dir = BASE_STORAGE_PATH / str(sess_uuid)
    session_dir.mkdir(parents=True, exist_ok=True)

    file_ext = os.path.splitext(original_filename)[1].lower()
    stored_filename = f"{uuid.uuid4().hex[:12]}_{original_filename}"
    target_path = session_dir / stored_filename

    file_size = 0
    with open(target_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):  # Chunks de 1MB
            file_size += len(chunk)
            FileSecurityValidator.validate_file_size(file_size)
            buffer.write(chunk)

    # 5. Procesamiento e inferencia de esquema con DuckDB / Polars Calamine
    try:
        total_rows, schema_preview = AttachmentAnalyticsEngine.process_and_inspect_file(
            file_path=str(target_path),
            mime_type=real_mime
        )
    except Exception as e:
        # Si falló la inspección, limpiar archivo en disco
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error al procesar el archivo tabular: {str(e)}"
        )

    # 6. Persistir registro en PostgreSQL
    attachment = ChatAttachmentModel(
        session_id=sess_uuid,
        user_id=user_id,
        filename=stored_filename,
        original_name=original_filename,
        mime_type=real_mime,
        file_size_bytes=file_size,
        storage_path=str(target_path),
        schema_preview=schema_preview,
        row_count=total_rows,
        status="ready"
    )
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)

    return AttachmentUploadResponse(
        id=str(attachment.id),
        session_id=str(attachment.session_id),
        filename=attachment.filename,
        original_name=attachment.original_name,
        mime_type=attachment.mime_type,
        file_size_bytes=attachment.file_size_bytes,
        row_count=attachment.row_count or total_rows,
        schema_preview=AttachmentSchemaPreview(**schema_preview),
        status=attachment.status,
        created_at=attachment.created_at.isoformat()
    )


@router.get(
    "/session/{session_id}",
    response_model=List[AttachmentSummarySchema],
    summary="Listar archivos adjuntos de una sesión"
)
async def list_session_attachments(
    session_id: str,
    user_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session)
):
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id inválido.")

    stmt = select(ChatAttachmentModel).where(ChatAttachmentModel.session_id == sess_uuid)
    if user_id:
        stmt = stmt.where(ChatAttachmentModel.user_id == user_id)
    stmt = stmt.order_by(ChatAttachmentModel.created_at.asc())

    rows = (await session.execute(stmt)).scalars().all()
    return [
        AttachmentSummarySchema(
            id=str(r.id),
            session_id=str(r.session_id),
            original_name=r.original_name,
            mime_type=r.mime_type,
            file_size_bytes=r.file_size_bytes,
            row_count=r.row_count,
            status=r.status,
            created_at=r.created_at.isoformat()
        )
        for r in rows
    ]


@router.delete(
    "/{attachment_id}",
    summary="Eliminar un archivo adjunto del chat"
)
async def delete_chat_attachment(
    attachment_id: str,
    user_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session)
):
    try:
        att_uuid = uuid.UUID(attachment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="attachment_id inválido.")

    att = await session.get(ChatAttachmentModel, att_uuid)
    if not att:
        raise HTTPException(status_code=404, detail="Archivo adjunto no encontrado.")

    if user_id and att.user_id != user_id:
        raise HTTPException(status_code=403, detail="No tienes permisos para eliminar este archivo.")

    # Eliminar archivo de disco
    try:
        if os.path.exists(att.storage_path):
            os.remove(att.storage_path)
    except Exception:
        pass

    await session.delete(att)
    await session.commit()

    return {"status": "deleted", "id": attachment_id}
