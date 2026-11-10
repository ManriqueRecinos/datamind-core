"""Clasificador de intención para enrutar entre Enseñanza a la IA, RAG de Procesos y Text-to-SQL."""

import re
from typing import Any, Dict, Literal
import unicodedata

IntentType = Literal["teach_knowledge", "process_qa", "data_query", "general_chat"]

TEACH_KNOWLEDGE_PATTERNS = [
    # Ej: "La tabla users se relaciona con la tabla companies uniendo users.current_company_id= companies.id"
    r"\bla\s+tabla\s+[a-z0-9_]+\s+se\s+(relaciona|une|vincula|conecta)\s+con\b",
    r"\blas\s+tablas\s+[a-z0-9_]+\s+y\s+[a-z0-9_]+\s+se\s+(relacionan|unen|vinculan)\b",
    r"\buniendo\s+[a-z0-9_]+\.[a-z0-9_]+\s*=\s*[a-z0-9_]+\.[a-z0-9_]+",
    # Ej: "Cuando el usuario pida datos o gráficos por empresa, nunca muestres... haz siempre JOIN..."
    r"\bcuando\s+(el\s+usuario|alguien|te|se)\s+(pida[n]?|pregunte[n]?|solicite[n]?|consulte[n]?)\b",
    r"\bnunca\s+muestres\s+[a-z0-9_]+\b",
    r"\bhaz\s+siempre\s+(inner\s+|left\s+)?join\b",
    # Comandos directos de aprendizaje / entrenamiento
    r"\b(aprende|recuerda|memoriza|guarda\s+esta\s+regla|ten\s+en\s+cuenta|ensename|ensenarte|te\s+enseno)\b",
    # Definiciones de estados o fórmulas de negocio
    r"\ben\s+la\s+tabla\s+[a-z0-9_]+[,:\s]+(el\s+campo|la\s+columna|el\s+estado)\s+[a-z0-9_]+\s+significa\b",
    r"\bsignifica\s+que\s+[a-z0-9_]+\s*=\s*['\"]?[a-z0-9_]+['\"]?",
    r"\bse\s+calcula\s+(restando|sumando|dividiendo|multiplicando)\b",
]

SQL_TRIGGER_PATTERNS = [
    r"\bcuant[oa]s?\b",
    r"\bcual(es)?\s+son\s+(l[ao]s|el)\b",
    r"\blist[ao]r?\b",
    r"\blistame\b",
    r"\bmuestrame\b",
    r"\bdame\b",
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
    r"\bgrafic[oa]s?\b",
    r"\bgraficar\b",
    r"\bchart[s]?\b",
    r"\bdiagrama[s]?\b",
    r"\bbarras\b",
    r"\bpastel\b",
    r"\btorta\b",
    r"\btendencia[s]?\b",
    r"\bcomparativa[s]?\b",
    r"\bmetrica[s]?\b",
    r"\bvinculad[oa]s?\b",
    r"\brelacionad[oa]s?\b",
    r"\brevisa(r|me)?\b",
    r"\banaliza(r|me)?\b",
    r"\brollo[s]?\b",
    r"\blote[s]?\b",
    r"\busuario[s]?\b",
    r"\buser[s]?\b",
    r"\bempresa[s]?\b",
    r"\bcompan(y|ies)\b",
    r"\bcliente[s]?\b",
    r"\beje\s+[xy]\b",
    r"\bagrup(ar|ado|ando)\b",
]

CHART_TRIGGER_PATTERNS = [
    r"\bgrafic[oa]s?\b",
    r"\bgraficar\b",
    r"\bgraficalo\b",
    r"\bchart[s]?\b",
    r"\bdiagrama[s]?\b",
    r"\bbarras\b",
    r"\bpastel\b",
    r"\btorta\b",
    r"\bdona\b",
    r"\blineas\b",
    r"\btendencia[s]?\b",
    r"\bvisualiza(r|cion)?\b",
    r"\bplot\b",
]

TABLE_TRIGGER_PATTERNS = [
    r"\b(haz(me)?|crea(me)?|genera(me)?|muestrame|dame|ver|mostrar)\s+(una?\s+|la\s+)?tabla\b",
    r"\ben\s+(una?\s+)?(tabla|formato\s+tabular)\b",
    r"\blist(a|ar|ame|ado)\b",
    r"\b(muestrame|dame|traeme|ver)\s+(todos?\s+)?(los\s+|las\s+)?(registros|filas|datos|usuarios|empresas|ordenes|rollos|clientes)\b",
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
    nfkd = unicodedata.normalize("NFKD", input_str or "")
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def _strip_conditional_clauses(normalized_text: str) -> str:
    """
    Elimina cláusulas condicionales o negativas (ej. 'cuando el usuario pida datos o gráficos...',
    'sin gráfico', 'no quiero gráfico') para evitar falsos positivos al detectar si pidió gráfico o tabla.
    """
    cleaned = re.sub(
        r"\bcuando\s+(el\s+usuario|alguien|te|se|yo)\s+(pida[n]?|pregunte[n]?|solicite[n]?|quiera[n]?)[^.;]*",
        " ",
        normalized_text
    )
    cleaned = re.sub(
        r"\b(sin|no\s+quiero|no\s+muestres|nunca\s+muestres)\s+(un\s+|una\s+|el\s+|la\s+)?(grafico[s]?|tabla[s]?)\b",
        " ",
        cleaned
    )
    return cleaned


class IntentClassifier:
    """Determina si el mensaje del usuario es una enseñanza a la IA, una consulta SQL, proceso o saludo."""

    @staticmethod
    def is_teaching_statement(prompt: str) -> bool:
        """
        Evalúa si el usuario le está enseñando una regla, relación JOIN, diccionario o fórmula a la IA
        en lugar de pedir que se ejecute una consulta en este momento.
        """
        raw = (prompt or "").strip()
        normalized = remove_accents(raw.lower())

        # Si es una pregunta interrogativa directa ("¿Cuántos...?", "¿Qué...?") no es una enseñanza declarativa
        if raw.startswith("¿") or raw.endswith("?"):
            # A menos que explícitamente diga "aprende que" o "recuerda que"
            if not re.search(r"\b(aprende|recuerda|memoriza|guarda\s+esta\s+regla)\b", normalized):
                return False

        for p in TEACH_KNOWLEDGE_PATTERNS:
            if re.search(p, normalized):
                return True

        return False

    @staticmethod
    def extract_teaching_capsule(prompt: str) -> Dict[str, Any]:
        """
        Analiza un texto de enseñanza escrito en el chat y extrae su categoría y metadatos estructurados:
        - `custom_relation`: si define cómo se unen dos tablas (ej. `users.current_company_id = companies.id`)
        - `sql_example`: si incluye una consulta `SELECT ...` de ejemplo
        - `kpi_formula`: si define una fórmula o cálculo
        - `business_rule`: regla de negocio, filtro o diccionario de estados
        """
        raw = (prompt or "").strip()
        norm = remove_accents(raw.lower())

        source_table = ""
        source_column = ""
        target_table = ""
        target_column = "id"
        label_column = ""

        # 1. Buscar patrón explícito `tablaA.colA = tablaB.colB`
        join_eq = re.search(r"\b([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\b", raw)
        if join_eq:
            source_table = join_eq.group(1)
            source_column = join_eq.group(2)
            target_table = join_eq.group(3)
            target_column = join_eq.group(4)

        # 2. Si no hubo `a.b = c.d`, buscar "La tabla X se relaciona con la tabla Y"
        if not source_table or not target_table:
            rel_tables = re.search(
                r"\btabla\s+([a-zA-Z0-9_]+)\s+se\s+(?:relaciona|une|vincula|conecta)\s+con\s+(?:la\s+tabla\s+)?([a-zA-Z0-9_]+)\b",
                raw,
                re.IGNORECASE
            )
            if rel_tables:
                source_table = source_table or rel_tables.group(1)
                target_table = target_table or rel_tables.group(2)

        # 3. Buscar columna descriptiva sugerida ("muestra empresa.name", "mostrar companies.name")
        show_col = re.search(
            r"\b(?:muestra|mostrar|selecciona|usa|usar)\s+(?:siempre\s+)?([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\b",
            raw,
            re.IGNORECASE
        )
        if show_col:
            label_column = show_col.group(2)
        else:
            show_simple = re.search(
                r"\b(?:muestra|mostrar|selecciona)\s+(?:el\s+campo\s+|la\s+columna\s+)?`?([a-zA-Z0-9_]+)`?\b",
                raw,
                re.IGNORECASE
            )
            if show_simple and show_simple.group(1).lower() not in ("el", "la", "los", "las", "siempre", "join"):
                label_column = show_simple.group(1)

        if source_table and target_table:
            src_col = source_column or f"{target_table.rstrip('s')}_id"
            tgt_col = target_column or "id"
            lbl_col = label_column or "name"
            join_hint = (
                f"JOIN {target_table} ON {source_table}.{src_col} = {target_table}.{tgt_col} "
                f"(mostrar {target_table}.{lbl_col} en vez de {src_col})"
            )
            return {
                "category": "custom_relation",
                "title": f"Relación Aprendida: {source_table}.{src_col} -> {target_table}.{tgt_col}",
                "source_table": source_table,
                "source_column": src_col,
                "target_table": target_table,
                "target_column": tgt_col,
                "label_column": lbl_col,
                "related_tables": [source_table, target_table],
                "join_hint": join_hint,
                "content": raw
            }

        if re.search(r"\bselect\s+.+\s+from\s+", norm):
            return {
                "category": "sql_example",
                "title": f"Ejemplo SQL Aprendido: {raw[:48]}...",
                "related_tables": [],
                "content": raw
            }

        if re.search(r"\b(se\s+calcula|formula|porcentaje|dividiendo|restando|multiplicando)\b", norm):
            return {
                "category": "kpi_formula",
                "title": f"Fórmula de Negocio: {raw[:48]}...",
                "related_tables": [],
                "content": raw
            }

        return {
            "category": "business_rule",
            "title": f"Regla de Negocio: {raw[:48]}...",
            "related_tables": [],
            "content": raw
        }

    @classmethod
    def classify(cls, prompt: str) -> IntentType:
        normalized = remove_accents((prompt or "").lower().strip())

        # 0. PRIORIDAD MÁXIMA: ¿El usuario le está enseñando una regla o relación a la IA?
        if cls.is_teaching_statement(prompt):
            return "teach_knowledge"

        # 1. Comprobar si requiere datos cuantitativos de la BD (prioridad alta)
        for p in SQL_TRIGGER_PATTERNS:
            if re.search(p, normalized):
                return "data_query"

        # 2. Comprobar saludos o preguntas generales
        for p in GREETING_PATTERNS:
            if re.search(p, normalized):
                return "general_chat"

        # 3. Por defecto, asumir consulta de procesos / RAG
        return "process_qa"

    @staticmethod
    def detect_chart_request(prompt: str) -> tuple[bool, str]:
        """
        Detecta si el usuario solicitó explícitamente un gráfico/visualización para la consulta actual
        (ignorando menciones condicionales como 'cuando el usuario pida gráficos...')
        y sugiere el tipo de gráfico inicial ('bar', 'line', 'doughnut', 'pie', 'horizontalBar').
        """
        if IntentClassifier.is_teaching_statement(prompt):
            return False, "bar"

        normalized = remove_accents((prompt or "").lower().strip())
        cleaned = _strip_conditional_clauses(normalized)

        wants_chart = any(re.search(p, cleaned) for p in CHART_TRIGGER_PATTERNS)
        if not wants_chart:
            return False, "bar"

        if re.search(r"\b(pastel|torta|circular|pie)\b", cleaned):
            return True, "pie"
        if re.search(r"\b(dona|anillo|doughnut)\b", cleaned):
            return True, "doughnut"
        if re.search(r"\b(linea[s]?|tendencia[s]?|evolucion|tiempo|fecha[s]?|mes)\b", cleaned):
            return True, "line"
        if re.search(r"\b(horizontal|ranking|top)\b", cleaned):
            return True, "horizontalBar"

        return True, "bar"

    @classmethod
    def detect_output_format(cls, prompt: str) -> Dict[str, Any]:
        """
        Determina explícitamente qué artefacto visual pidió el usuario:
        - `wants_chart`: True solo si pidió un gráfico/visualización.
        - `wants_table`: True solo si pidió una tabla/listado de registros.
        - `output_mode`: 'chart' | 'table' | 'both' | 'text_only'
        """
        if cls.is_teaching_statement(prompt):
            return {
                "wants_chart": False,
                "wants_table": False,
                "preferred_chart_type": "bar",
                "output_mode": "text_only"
            }

        wants_chart, pref_type = cls.detect_chart_request(prompt)
        normalized = remove_accents((prompt or "").lower().strip())
        cleaned = _strip_conditional_clauses(normalized)

        wants_table = any(re.search(p, cleaned) for p in TABLE_TRIGGER_PATTERNS)

        if wants_chart and wants_table:
            mode = "both"
        elif wants_chart:
            mode = "chart"
        elif wants_table:
            mode = "table"
        else:
            mode = "text_only"

        return {
            "wants_chart": wants_chart,
            "wants_table": wants_table,
            "preferred_chart_type": pref_type,
            "output_mode": mode
        }
