"""Casos de uso para Compilación, Parseo, Validación y Dry-Run del Constructor de Consultas (Query Blueprint).

Utiliza `sqlglot` como motor AST canónico y `SQLGuardrail` para el aislamiento de seguridad.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import re
import uuid
import sqlglot
from sqlglot import exp, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.query_blueprint import (
    BaseTableSpec,
    JoinSpec,
    JoinType,
    OnCondition,
    OrderByItem,
    QueryBlueprint,
    RawBlock,
    SelectItem,
    SingleSelectBlueprint,
    UnionMode,
    UnionSpec,
    WhereCondition,
)
from app.infrastructure.database.models import DatabaseConnectionModel
from app.infrastructure.llm.sql_guardrail import SQLGuardrail, SQLSecurityViolation
from app.use_cases.manage_connections import ManageConnectionsUseCase


class QueryBlueprintUseCase:
    """Orquesta la compilación bidireccional, validación semántica y ejecución de prueba de blueprints SQL."""

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
        self.guardrail = SQLGuardrail(max_limit=20)

    # =========================================================================
    # 1. COMPILACIÓN: QueryBlueprint -> SQL String
    # =========================================================================
    def compile(self, blueprint: QueryBlueprint, dialect: str = "postgres") -> str:
        """
        Compila un QueryBlueprint a una sentencia SQL limpia en el dialecto especificado.
        Preserva bloques crudos (ej. CTEs al inicio si existen).
        """
        target_dialect = "postgres" if dialect.lower() in ("postgres", "postgresql", "pgsql") else "mysql"

        # 1. Compilar consulta primaria
        primary_ast = self._compile_single_select(blueprint.primary, target_dialect)

        # 2. Encadenar operaciones UNION
        current_ast = primary_ast
        for union_elem in blueprint.unions:
            branch_ast = self._compile_single_select(union_elem.select_query, target_dialect)
            distinct_flag = (union_elem.mode == UnionMode.UNION)
            current_ast = current_ast.union(branch_ast, distinct=distinct_flag)

        # 3. Incorporar raw_blocks de tipo CTE (WITH) si existen
        cte_blocks = [b.content.strip() for b in blueprint.raw_blocks if b.type == "cte"]
        base_sql = current_ast.sql(target_dialect, pretty=True)

        if cte_blocks:
            combined_ctes = ",\n".join(cte_blocks)
            if not combined_ctes.upper().startswith("WITH"):
                combined_ctes = f"WITH {combined_ctes}"
            base_sql = f"{combined_ctes}\n{base_sql}"

        return base_sql.strip()

    def _compile_single_select(self, query: SingleSelectBlueprint, dialect: str) -> exp.Select:
        """Compila un SingleSelectBlueprint a un objeto exp.Select de sqlglot."""
        # 1. Proyecciones (SELECT)
        select_exprs = []
        if query.select:
            for item in query.select:
                expr_str = item.expr.strip()
                if item.agg and item.agg.upper() in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
                    expr_str = f"{item.agg.upper()}({expr_str})"

                if item.alias and item.alias.strip():
                    select_exprs.append(f"{expr_str} AS {item.alias.strip()}")
                else:
                    select_exprs.append(expr_str)
        else:
            select_exprs.append("*")

        select_ast = select(*select_exprs)

        # 2. Cláusula FROM
        base_table = query.base.table.strip()
        if query.base.alias and query.base.alias.strip():
            from_target = f"{base_table} AS {query.base.alias.strip()}"
        else:
            from_target = base_table
        select_ast = select_ast.from_(from_target)

        # 3. Cláusulas JOIN
        for j in query.joins:
            j_table = j.table.strip()
            if j.alias and j.alias.strip():
                j_target = f"{j_table} AS {j.alias.strip()}"
            else:
                j_target = j_table

            # Construir condiciones ON
            on_clauses = []
            for cond in j.on:
                op = cond.op.strip() if cond.op else "="
                on_clauses.append(f"{cond.left.strip()} {op} {cond.right.strip()}")

            on_str = " AND ".join(on_clauses) if on_clauses else "1 = 1"
            join_type_str = j.type.value if hasattr(j.type, "value") else str(j.type)

            select_ast = select_ast.join(
                j_target,
                on=on_str,
                join_type=join_type_str
            )

        # 4. Cláusula WHERE
        if query.where:
            where_parts = []
            for idx, w in enumerate(query.where):
                op = w.op.strip().upper() if w.op else "="
                left = w.left.strip()
                val = w.value

                if op in ("IS NULL", "IS NOT NULL"):
                    part = f"{left} {op}"
                elif op == "IN":
                    if isinstance(val, (list, tuple)):
                        vals_str = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in val)
                        part = f"{left} IN ({vals_str})"
                    else:
                        part = f"{left} IN ({val})"
                else:
                    # Si el valor tiene formato alias.columna (identificador SQL) o número, no entrecomillar
                    is_identifier_ref = isinstance(val, str) and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*$", val)
                    is_numeric = isinstance(val, str) and re.match(r"^-?\d+(?:\.\d+)?$", val)

                    if isinstance(val, str) and not is_identifier_ref and not is_numeric and not (val.startswith("'") and val.endswith("'")):
                        part = f"{left} {op} '{val}'"
                    else:
                        part = f"{left} {op} {val}"

                if idx == 0:
                    where_parts.append(part)
                else:
                    logic = w.logic.strip().upper() if w.logic else "AND"
                    where_parts.append(f"{logic} {part}")

            full_where_sql = " ".join(where_parts)
            select_ast = select_ast.where(full_where_sql)

        # 5. Cláusula GROUP BY
        if query.group_by:
            select_ast = select_ast.group_by(*[g.strip() for g in query.group_by if g.strip()])

        # 6. Cláusula ORDER BY
        if query.order_by:
            order_items = []
            for o in query.order_by:
                direction = o.direction.strip().upper() if o.direction else "ASC"
                order_items.append(f"{o.expr.strip()} {direction}")
            select_ast = select_ast.order_by(*order_items)

        # 7. Cláusula LIMIT
        if query.limit is not None and query.limit > 0:
            select_ast = select_ast.limit(min(query.limit, 1000))

        return select_ast

    # =========================================================================
    # 2. PARSEO: SQL String -> QueryBlueprint + raw_blocks
    # =========================================================================
    def parse(self, raw_sql: str, dialect: str = "postgres") -> QueryBlueprint:
        """
        Analiza sintácticamente una consulta SQL usando sqlglot y genera un QueryBlueprint estructurado.
        Cualquier fragmento no representable (CTEs, subconsultas complejas) se almacena en raw_blocks.
        """
        target_dialect = "postgres" if dialect.lower() in ("postgres", "postgresql", "pgsql") else "mysql"
        cleaned_sql = SQLGuardrail.extract_sql_query(raw_sql)
        if not cleaned_sql:
            raise ValueError("La consulta SQL suministrada está vacía.")

        try:
            parsed = sqlglot.parse_one(cleaned_sql, read=target_dialect)
        except Exception:
            try:
                parsed = sqlglot.parse_one(cleaned_sql)
            except Exception as e:
                raise ValueError(f"Error sintáctico SQL: {str(e)}")

        # Validar que no contenga sentencias destructivas o no-SELECT
        if isinstance(parsed, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create, exp.TruncateTable, exp.Command)):
            raise ValueError(f"Operación no permitida: {type(parsed).__name__}. Solo se permiten consultas de lectura.")

        raw_blocks: List[RawBlock] = []

        # Extraer CTE si existe en la raíz
        with_clause = parsed.args.get("with_") or parsed.args.get("with")
        if with_clause:
            raw_blocks.append(
                RawBlock(
                    id=f"cte_{uuid.uuid4().hex[:8]}",
                    type="cte",
                    title="Common Table Expression (WITH)",
                    content=with_clause.sql(target_dialect)
                )
            )

        # Manejo de árboles con UNION / UNION ALL
        if isinstance(parsed, exp.Union):
            branches = self._flatten_unions(parsed)
            primary_bp = self._parse_single_select(branches[0][1], target_dialect)
            unions_list: List[UnionSpec] = []
            for mode, branch_select in branches[1:]:
                sub_bp = self._parse_single_select(branch_select, target_dialect)
                unions_list.append(UnionSpec(mode=mode, select_query=sub_bp))

            return QueryBlueprint(
                version="1.0",
                primary=primary_bp,
                unions=unions_list,
                raw_blocks=raw_blocks
            )
        elif isinstance(parsed, exp.Select):
            primary_bp = self._parse_single_select(parsed, target_dialect)
            return QueryBlueprint(
                version="1.0",
                primary=primary_bp,
                unions=[],
                raw_blocks=raw_blocks
            )
        else:
            raise ValueError("La sentencia analizada debe ser un SELECT o una combinación de UNIONs.")

    def _flatten_unions(self, union_ast: exp.Union) -> List[Tuple[UnionMode, exp.Select]]:
        """Desenrolla recursivamente un árbol de uniones a una lista ordenada de (modo, select)."""
        nodes: List[Tuple[UnionMode, exp.Expression]] = []

        def recurse(node: exp.Expression, incoming_mode: UnionMode):
            if isinstance(node, exp.Union):
                distinct = node.args.get("distinct", False)
                mode = UnionMode.UNION if distinct else UnionMode.UNION_ALL
                recurse(node.this, incoming_mode)
                recurse(node.expression, mode)
            else:
                nodes.append((incoming_mode, node))

        initial_distinct = union_ast.args.get("distinct", False)
        initial_mode = UnionMode.UNION if initial_distinct else UnionMode.UNION_ALL
        recurse(union_ast.this, initial_mode)
        recurse(union_ast.expression, initial_mode)

        result: List[Tuple[UnionMode, exp.Select]] = []
        for mode, n in nodes:
            if isinstance(n, exp.Select):
                result.append((mode, n))
            else:
                # Si una rama es una subconsulta entre paréntesis u otra expresión
                result.append((mode, n.unalias() if hasattr(n, "unalias") else n))
        return result

    def _parse_single_select(self, ast_select: exp.Select, dialect: str) -> SingleSelectBlueprint:
        """Convierte un nodo exp.Select en un SingleSelectBlueprint."""
        # 1. Tabla base (FROM)
        from_node = ast_select.args.get("from_") or ast_select.args.get("from")
        if not from_node or not from_node.this:
            base_spec = BaseTableSpec(table="", alias=None)
        else:
            table_target = from_node.this
            base_spec = BaseTableSpec(
                table=table_target.name if hasattr(table_target, "name") and table_target.name else str(table_target),
                alias=table_target.alias if hasattr(table_target, "alias") and table_target.alias else None
            )

        # 2. JOINs
        joins_list: List[JoinSpec] = []
        for j in ast_select.args.get("joins", []):
            j_this = j.this
            j_table = j_this.name if hasattr(j_this, "name") else str(j_this)
            j_alias = j_this.alias if hasattr(j_this, "alias") and j_this.alias else None

            # Determinar JoinType
            side = (j.side or "").upper()
            kind = (j.kind or "").upper()

            if side == "LEFT":
                j_type = JoinType.LEFT
            elif side == "RIGHT":
                j_type = JoinType.RIGHT
            elif side == "FULL":
                j_type = JoinType.FULL
            elif kind == "CROSS":
                j_type = JoinType.CROSS
            else:
                j_type = JoinType.INNER

            # Analizar ON
            on_conditions: List[OnCondition] = []
            on_expr = j.args.get("on")
            if on_expr:
                conditions = self._flatten_conditions(on_expr)
                for cond in conditions:
                    if isinstance(cond, exp.Binary):
                        op = cond.key.upper() if hasattr(cond, "key") else "="
                        if isinstance(cond, exp.EQ):
                            op = "="
                        elif isinstance(cond, exp.NEQ):
                            op = "!="
                        elif isinstance(cond, exp.GT):
                            op = ">"
                        elif isinstance(cond, exp.GTE):
                            op = ">="
                        elif isinstance(cond, exp.LT):
                            op = "<"
                        elif isinstance(cond, exp.LTE):
                            op = "<="

                        on_conditions.append(
                            OnCondition(
                                left=cond.this.sql(dialect),
                                op=op,
                                right=cond.expression.sql(dialect)
                            )
                        )
                    else:
                        on_conditions.append(
                            OnCondition(
                                left=cond.sql(dialect),
                                op="=",
                                right="1"
                            )
                        )

            joins_list.append(
                JoinSpec(
                    type=j_type,
                    table=j_table,
                    alias=j_alias,
                    on=on_conditions
                )
            )

        # 3. SELECT (proyecciones)
        select_items: List[SelectItem] = []
        for s in ast_select.expressions:
            if isinstance(s, exp.Alias):
                alias_name = s.alias
                inner_expr = s.this
            else:
                alias_name = None
                inner_expr = s

            # Detectar agregaciones comunes
            agg_name = None
            if isinstance(inner_expr, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)):
                agg_name = inner_expr.key.upper()
                inner_str = inner_expr.this.sql(dialect) if inner_expr.this else "*"
            else:
                inner_str = inner_expr.sql(dialect)

            select_items.append(
                SelectItem(
                    expr=inner_str,
                    alias=alias_name,
                    agg=agg_name
                )
            )

        # 4. WHERE
        where_items: List[WhereCondition] = []
        where_node = ast_select.args.get("where")
        if where_node and where_node.this:
            conds = self._flatten_conditions(where_node.this)
            for idx, c in enumerate(conds):
                if isinstance(c, exp.Binary):
                    op = "="
                    if isinstance(c, exp.EQ):
                        op = "="
                    elif isinstance(c, exp.NEQ):
                        op = "!="
                    elif isinstance(c, exp.GT):
                        op = ">"
                    elif isinstance(c, exp.GTE):
                        op = ">="
                    elif isinstance(c, exp.LT):
                        op = "<"
                    elif isinstance(c, exp.LTE):
                        op = "<="
                    elif isinstance(c, exp.Like):
                        op = "LIKE"
                    elif isinstance(c, exp.ILike):
                        op = "ILIKE"

                    val_raw = c.expression.sql(dialect).strip("'")
                    where_items.append(
                        WhereCondition(
                            left=c.this.sql(dialect),
                            op=op,
                            value=val_raw,
                            logic="AND"
                        )
                    )
                else:
                    where_items.append(
                        WhereCondition(
                            left=c.sql(dialect),
                            op="=",
                            value="1",
                            logic="AND"
                        )
                    )

        # 5. GROUP BY
        group_items: List[str] = []
        group_node = ast_select.args.get("group")
        if group_node and group_node.expressions:
            for g in group_node.expressions:
                group_items.append(g.sql(dialect))

        # 6. ORDER BY
        order_items: List[OrderByItem] = []
        order_node = ast_select.args.get("order")
        if order_node and order_node.expressions:
            for o in order_node.expressions:
                direction = "DESC" if getattr(o, "desc", False) else "ASC"
                expr_text = o.this.sql(dialect) if hasattr(o, "this") else o.sql(dialect)
                order_items.append(OrderByItem(expr=expr_text, direction=direction))

        # 7. LIMIT
        limit_val = None
        limit_node = ast_select.args.get("limit")
        if limit_node and limit_node.expression:
            try:
                limit_val = int(limit_node.expression.this)
            except Exception:
                pass

        return SingleSelectBlueprint(
            base=base_spec,
            joins=joins_list,
            select=select_items,
            where=where_items,
            group_by=group_items,
            order_by=order_items,
            limit=limit_val
        )

    def _flatten_conditions(self, node: exp.Expression) -> List[exp.Expression]:
        """Descompone recursivamente expresiones And en lista de condiciones planas."""
        if isinstance(node, exp.And):
            return self._flatten_conditions(node.this) + self._flatten_conditions(node.expression)
        return [node]

    # =========================================================================
    # 3. VALIDACIÓN SEMÁNTICA: Esquema Vectorizado
    # =========================================================================
    async def validate(self, blueprint: QueryBlueprint, connection_id: str) -> Dict[str, Any]:
        """
        Valida que:
        1. Las tablas utilizadas existan en la conexión y estén en `synced_tables`.
        2. Las columnas referenciadas existan en la introspección de dichas tablas.
        3. En caso de UNIONs, ambas ramas tengan el mismo número de columnas proyectadas.
        """
        if not self.session:
            raise ValueError("Se requiere una sesión de base de datos activa para validar esquemas.")

        conn_uuid = uuid.UUID(str(connection_id))
        conn_model = await self.session.get(DatabaseConnectionModel, conn_uuid)
        if not conn_model:
            return {
                "is_valid": False,
                "errors": [f"Conexión con ID '{connection_id}' no encontrada."],
                "warnings": []
            }

        synced_tables = {t.lower(): t for t in (conn_model.synced_tables or [])}
        manage_conn = ManageConnectionsUseCase(self.session)
        introspect_info = await manage_conn.get_connection_tables(connection_id)
        schema_tables = {t["table_name"].lower(): t for t in introspect_info.get("tables", [])}

        errors: List[str] = []
        warnings: List[str] = []

        all_selects = [blueprint.primary] + [u.select_query for u in blueprint.unions]

        for idx, sel in enumerate(all_selects):
            branch_name = f"Consulta {'Primaria' if idx == 0 else f'UNION #{idx}'}"
            base_t = sel.base.table.strip()

            if not base_t:
                errors.append(f"{branch_name}: Debe especificar una tabla base (FROM).")
            else:
                if base_t.lower() not in synced_tables:
                    errors.append(f"{branch_name}: La tabla base '{base_t}' no está vectorizada en la conexión.")
                elif base_t.lower() not in schema_tables:
                    warnings.append(f"{branch_name}: La tabla base '{base_t}' no se encuentra en el esquema accesible.")

            for j_idx, j in enumerate(sel.joins):
                j_t = j.table.strip()
                if not j_t:
                    errors.append(f"{branch_name}, Unión #{j_idx + 1}: Debe especificar la tabla a unir.")
                else:
                    if j_t.lower() not in synced_tables:
                        errors.append(f"{branch_name}, Unión #{j_idx + 1}: La tabla '{j_t}' no está vectorizada.")

            # Chequeo de columnas en proyecciones
            table_cols_map: Dict[str, List[str]] = {}
            for t_key in [base_t] + [j.table.strip() for j in sel.joins]:
                if t_key.lower() in schema_tables:
                    table_cols_map[t_key.lower()] = [
                        c["name"].lower() for c in schema_tables[t_key.lower()]["columns"]
                    ]

        # Validar consistencia de columnas en UNION
        if blueprint.unions:
            primary_col_count = len(blueprint.primary.select) or 1
            for u_idx, u in enumerate(blueprint.unions):
                u_count = len(u.select_query.select) or 1
                if u_count != primary_col_count:
                    errors.append(
                        f"Inconsistencia en UNION #{u_idx + 1}: La consulta primaria proyecta "
                        f"{primary_col_count} columnas, pero esta unión proyecta {u_count} columnas."
                    )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    # =========================================================================
    # 4. DRY RUN: Prueba segura (LIMIT 20)
    # =========================================================================
    async def dry_run(self, sql_query: str, connection_id: str) -> Dict[str, Any]:
        """
        Ejecuta de manera segura la consulta SQL en la base de datos destino con LIMIT 20 forzado.
        """
        if not self.session:
            raise ValueError("Se requiere una sesión activa para ejecutar el dry-run.")

        conn_uuid = uuid.UUID(str(connection_id))
        conn_model = await self.session.get(DatabaseConnectionModel, conn_uuid)
        if not conn_model:
            raise ValueError(f"Conexión con ID '{connection_id}' no encontrada.")

        manage_conn = ManageConnectionsUseCase(self.session)
        adapter = manage_conn._build_adapter(conn_model)

        # 1. Sanitizar y validar seguridad con SQLGuardrail
        is_safe, sanitized_sql, err = self.guardrail.validate_and_sanitize(
            sql_query,
            dialect=adapter.sqlglot_dialect
        )
        if not is_safe:
            return {
                "success": False,
                "error": f"Guardrail de seguridad: {err}",
                "rows": [],
                "columns": [],
                "row_count": 0,
                "sql_executed": sql_query
            }

        # 2. Forzar estrictamente LIMIT 20 si es necesario
        try:
            parsed = sqlglot.parse_one(sanitized_sql, read=adapter.sqlglot_dialect)
            parsed = parsed.limit(20)
            final_sql = parsed.sql(adapter.sqlglot_dialect)
        except Exception:
            final_sql = sanitized_sql

        # 3. Ejecutar consulta en la conexión dinámica
        try:
            rows = await adapter.execute_query(final_sql)
            columns = list(rows[0].keys()) if rows else []
            return {
                "success": True,
                "error": None,
                "rows": rows,
                "columns": columns,
                "row_count": len(rows),
                "sql_executed": final_sql
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error de ejecución en base remota: {str(e)}",
                "rows": [],
                "columns": [],
                "row_count": 0,
                "sql_executed": final_sql
            }
