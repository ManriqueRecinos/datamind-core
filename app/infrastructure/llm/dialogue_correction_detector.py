"""Detector asíncrono de correcciones de esquema en diálogo usando Ollama."""

import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx
from app.infrastructure.llm.prescriptive_condition_validator import PrescriptiveConditionValidator

logger = logging.getLogger("dialogue_detector")


class DialogueCorrectionDetector:
    """
    Analiza el diálogo previo, valida contra el catálogo de entidades y extrae
    candidatos estructurados con tope de 120 tokens en Ollama.
    """

    SYSTEM_PROMPT = """Eres un analizador semántico estricto de bases de datos.
Tu tarea es evaluar el mensaje del usuario y determinar si está corrigiendo o especificando una condición obligatoria sobre una tabla o columna para futuras consultas.

Tablas y columnas válidas del catálogo:
{catalog_context}

Reglas estrictas:
1. Si el usuario NO está corrigiendo una tabla/columna (ej. agradece, saluda, queja general, o pregunta nueva), responde exactamente:
{{"has_correction": false}}

2. Si el usuario corrige una condición o filtro de una tabla y columna válida, responde con este JSON exacto:
{{
  "has_correction": true,
  "knowledge_type": "schema_correction",
  "target_entity": "<nombre_exacto_tabla>",
  "target_column": "<nombre_exacto_columna>",
  "prescriptive_condition": "<expresion_booleana_sql_simple>",
  "explanation": "<resumen_breve>"
}}

No agregues texto explicativo, solo el JSON. Máximo 100 tokens."""

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434", model: str = "qwen2.5:3b"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    def build_catalog_context(self, synced_tables: List[Dict[str, Any]]) -> str:
        """Formatea el catálogo en un resumen compacto para el prompt."""
        lines = []
        for t in synced_tables[:25]:
            t_name = t.get("name") or t.get("table_name") or ""
            cols = [c.get("name") for c in t.get("columns", []) if isinstance(c, dict)]
            if t_name:
                lines.append(f"- {t_name} ({', '.join(cols[:10])})")
        return "\n".join(lines) if lines else "- (No hay catálogo cargado)"

    async def detect_correction(
        self,
        user_message: str,
        previous_assistant_message: Optional[str],
        previous_sql: Optional[str],
        synced_tables: List[Dict[str, Any]],
        dialect: str = "mysql",
        cancel_token: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Ejecuta la inferencia en Ollama y valida estrictamente la salida.
        """
        catalog_str = self.build_catalog_context(synced_tables)
        prompt = self.SYSTEM_PROMPT.format(catalog_context=catalog_str)

        user_content = f"Turno anterior del asistente:\nRespuesta: {previous_assistant_message or 'N/A'}\nSQL generado: {previous_sql or 'N/A'}\n\nMensaje actual del usuario:\n{user_message}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ],
            "options": {
                "temperature": 0.0,
                "num_predict": 120
            },
            "stream": False
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{self.ollama_url}/api/chat", json=payload)
                if res.status_code != 200:
                    logger.warning(f"Ollama returned status {res.status_code}: {res.text}")
                    return None

                data = res.json()
                content = data.get("message", {}).get("content", "").strip()

                # Extraer JSON de la respuesta
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if not match:
                    return None

                parsed = json.loads(match.group(0))
                if not parsed.get("has_correction"):
                    return None

                target_entity = (parsed.get("target_entity") or "").strip().lower()
                target_column = (parsed.get("target_column") or "").strip().lower()
                prescriptive_condition = (parsed.get("prescriptive_condition") or "").strip()

                if not target_entity or not target_column or not prescriptive_condition:
                    return None

                # Validar existencia en catálogo
                entity_found = False
                col_found = False
                for t in synced_tables:
                    t_name = (t.get("name") or t.get("table_name") or "").strip().lower()
                    if t_name == target_entity:
                        entity_found = True
                        cols = [(c.get("name") or "").strip().lower() for c in t.get("columns", []) if isinstance(c, dict)]
                        if target_column in cols:
                            col_found = True
                        break

                if not entity_found or not col_found:
                    logger.info(f"Descartada corrección: {target_entity}.{target_column} no existe en catálogo.")
                    return None

                # Validar prescriptive_condition con sqlglot
                is_valid, norm_cond, err = PrescriptiveConditionValidator.validate_and_normalize(
                    prescriptive_condition, target_column, dialect=dialect
                )
                if not is_valid:
                    logger.warning(f"Condición rechazada por sqlglot: {err}")
                    return None

                # Sintetizar texto estructurado formal (Anti prompt injection)
                synthesized_text = f"Para la tabla `{target_entity}`, la columna `{target_column}` debe cumplir: {norm_cond}."

                return {
                    "knowledge_type": parsed.get("knowledge_type", "schema_correction"),
                    "title": f"Filtro en {target_entity}.{target_column}",
                    "content": synthesized_text,
                    "target_entity": target_entity,
                    "target_column": target_column,
                    "prescriptive_condition": norm_cond,
                    "explanation": parsed.get("explanation", "Corrección aprendida del diálogo")
                }

        except Exception as e:
            logger.error(f"Error en DialogueCorrectionDetector: {str(e)}")
            return None
