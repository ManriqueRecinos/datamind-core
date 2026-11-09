"""Configuración de logging estructurado con formato JSON y Correlation IDs."""

import json
import logging
import re
import sys
from datetime import datetime, timezone

SENSITIVE_PATTERNS = [
    (re.compile(r'(password=)[^\s&]+', re.IGNORECASE), r'\1***'),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9_\-\.]+', re.IGNORECASE), r'\1***'),
    (re.compile(r'(postgresql\+asyncpg://[^:]+:)[^@]+(@)', re.IGNORECASE), r'\1***\2'),
]


def mask_sensitive_data(text: str) -> str:
    """Oculta contraseñas y tokens en cadenas de texto."""
    for pattern, repl in SENSITIVE_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class JSONFormatter(logging.Formatter):
    """Formateador que serializa registros de log en JSON estructurado con ofuscación de credenciales."""

    def format(self, record: logging.LogRecord) -> str:
        msg = mask_sensitive_data(record.getMessage())
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": msg,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id
        if record.exc_info:
            log_obj["exception"] = mask_sensitive_data(self.formatException(record.exc_info))
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configura el logger raíz para salida estándar estructurada."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers = [handler]
