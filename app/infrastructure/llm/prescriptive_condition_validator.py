"""Validador sintáctico estricto de condiciones prescriptivas mediante sqlglot."""

import re
from typing import Tuple, Optional
import sqlglot
from sqlglot import exp


class PrescriptiveConditionValidator:
    """
    Valida que una prescriptive_condition extraída por el detector sea una expresión
    booleana estricta, segura, referida únicamente a la columna objetivo y sin inyecciones por literales.
    """

    SAFE_LITERAL_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\s]+$")
    MAX_CONDITION_LENGTH = 250
    MAX_LITERAL_LENGTH = 35

    @classmethod
    def validate_and_normalize(
        cls,
        condition: str,
        target_column: str,
        dialect: str = "mysql"
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Valida sintáctica y semánticamente la condición.
        Retorna (is_valid, normalized_ast_sql, error_message).
        """
        if not condition or not condition.strip():
            return False, None, "Condición vacía."

        raw = condition.strip()

        # 1. Longitud máxima
        if len(raw) > cls.MAX_CONDITION_LENGTH:
            return False, None, f"La condición excede la longitud máxima de {cls.MAX_CONDITION_LENGTH} caracteres."

        # 2. Prohibir punto y coma y comentarios SQL
        if ";" in raw or "--" in raw or "/*" in raw:
            return False, None, "Caracteres no permitidos (; o comentarios SQL) en la condición."

        # 3. Parsear con sqlglot usando el dialecto de la conexión
        try:
            # sqlglot.parse_one
            parsed = sqlglot.parse_one(raw, read=dialect)
        except Exception as e:
            return False, None, f"Error de sintaxis SQL al parsear condición: {str(e)}"

        if parsed is None:
            return False, None, "No se pudo interpretar como expresión SQL válida."

        # 4. Prohibir sentencias completas (SELECT, INSERT, UPDATE, DROP, etc.)
        if isinstance(parsed, (exp.Select, exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter)):
            return False, None, "La condición no puede ser una sentencia SQL completa, debe ser una expresión booleana."

        # 5. Prohibir subconsultas
        if list(parsed.find_all(exp.Select)):
            return False, None, "Subconsultas no permitidas en la condición."

        # 6. Prohibir llamadas a funciones del sistema (e.g. sleep, benchmark, version, user, load_file)
        forbidden_funcs = {"sleep", "benchmark", "version", "user", "database", "schema", "load_file", "exec", "system"}
        for func in parsed.find_all(exp.Anonymous):
            if func.name.lower() in forbidden_funcs:
                return False, None, f"Función del sistema prohibida: {func.name}"

        # 7. Verificar que las columnas referenciadas coincidan con target_column
        columns = [c.name.lower() for c in parsed.find_all(exp.Column)]
        if not columns:
            # Si no hay identificador de columna explícito, puede ser IS NOT NULL implícito
            pass
        else:
            norm_target = target_column.lower().strip()
            for col in columns:
                if col != norm_target:
                    return False, None, f"La condición referencia una columna ajena '{col}' distinta de la objetivo '{norm_target}'."

        # 8. Validar literales de texto (Anti Prompt Injection por literal)
        for literal in parsed.find_all(exp.Literal):
            val = str(literal.this)
            if len(val) > cls.MAX_LITERAL_LENGTH:
                return False, None, f"El literal '{val[:20]}...' excede el límite de {cls.MAX_LITERAL_LENGTH} caracteres."
            if not cls.SAFE_LITERAL_REGEX.match(val):
                return False, None, f"El literal contiene caracteres no permitidos o sospechosos: '{val}'"

        # 9. Retornar SQL normalizado determinista
        normalized_sql = parsed.sql(dialect=dialect)
        return True, normalized_sql, None
