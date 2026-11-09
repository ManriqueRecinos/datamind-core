"""Clasificador de intención para enrutar entre RAG de Procesos y Text-to-SQL de MariaDB."""

import re
import unicodedata
from typing import Literal

IntentType = Literal["process_qa", "data_query", "general_chat"]

SQL_TRIGGER_PATTERNS = [
    r"\bcuant[oa]s?\b",
    r"\bcual(es)?\s+son\s+(l[ao]s|el)\b",
    r"\blist[ao]r?\b",
    r"\borden(es)?\b",
    r"\bretraso[s]?\b",
    r"\bdemora[s]?\b",
    r"\btabla[s]?\b",
    r"\bregistro[s]?\b",
    r"\bpromedio\b",
    r"\btotal(es)?\b",
    r"\bmaximo[s]?\b",
    r"\bminimo[s]?\b",
    r"\bultim[oa]s?\b",
    r"\bprimer[oa]s?\b",
    r"\bpendientes?\b",
    r"\bestado\b",
]

GREETING_PATTERNS = [
    r"\bhola\b",
    r"\bbuenos\s+dias\b",
    r"\bbuenas\s+tardes\b",
    r"\bbuenas\s+noches\b",
    r"\bsaludos\b",
    r"\bque\s+tal\b",
    r"\bquien\s+eres\b",
    r"\bcomo\s+estas\b",
    r"\bcomo\s+te\s+llamas\b"
]


def remove_accents(input_str: str) -> str:
    """Remueve tildes y diacríticos para robustez en búsquedas en español."""
    nfkd = unicodedata.normalize("NFKD", input_str)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


class IntentClassifier:
    """Determina si la consulta requiere consultar tablas de MariaDB o conocimiento de procesos."""

    @staticmethod
    def classify(prompt: str) -> IntentType:
        normalized = remove_accents(prompt.lower().strip())

        # 1. Comprobar si requiere datos cuantitativos de MariaDB (prioridad alta)
        for p in SQL_TRIGGER_PATTERNS:
            if re.search(p, normalized):
                return "data_query"

        # 2. Comprobar saludos o preguntas generales
        for p in GREETING_PATTERNS:
            if re.search(p, normalized):
                return "general_chat"

        # 3. Por defecto, asumir consulta de procesos / RAG
        return "process_qa"
