"""Generador asíncrono de eventos Server-Sent Events (SSE) para streaming en tiempo real."""

import json
from typing import AsyncIterator, Dict, Any


def format_sse(event_type: str, data: Dict[str, Any]) -> str:
    """Da formato a un bloque de evento conforme al estándar SSE."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"
