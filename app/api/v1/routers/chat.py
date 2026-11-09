"""Endpoints para la conversación de chat y streaming en tiempo real (SSE)."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.schemas.chat import ChatRequest, ChatResponse
from app.api.v1.streaming import format_sse
from app.infrastructure.database.postgres_adapter import get_db_session
from app.use_cases.ask_chat import AskChatUseCase

router = APIRouter(prefix="/chat", tags=["Chat & Text-to-SQL"])


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
            connection_id=payload.connection_id
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
    """Transmite la respuesta token a token usando Server-Sent Events (SSE)."""
    async def sse_generator():
        use_case = AskChatUseCase(session)
        # Emitir sesión iniciada
        yield format_sse("session", {"status": "processing"})

        try:
            result = await use_case.execute_sync(
                prompt=payload.prompt,
                session_id=payload.session_id,
                user_id=payload.user_id or "user",
                connection_id=payload.connection_id
            )

            # Transmitir el mensaje en tokens para la animación
            tokens = result["message"].split(" ")
            for idx, token in enumerate(tokens):
                separator = " " if idx < len(tokens) - 1 else ""
                yield format_sse("token", {"text": token + separator})

            # Si produjo datos tabulares, emitir el evento dataset para habilitar el botón de Excel
            if result.get("has_tabular_data") and result.get("dataset_id"):
                yield format_sse("dataset", {
                    "dataset_id": result["dataset_id"],
                    "row_count": result.get("row_count", 0),
                    "columns": result.get("columns", []),
                    "preview_rows": result.get("preview_rows", []),
                    "sql": result.get("generated_sql")
                })

            # Emitir evento de finalización
            yield format_sse("done", {
                "session_id": result["session_id"],
                "latency_ms": result["latency_ms"]
            })
        except Exception as e:
            yield format_sse("error", {"detail": str(e)})

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
