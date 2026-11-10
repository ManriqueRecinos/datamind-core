"""Adaptador dinámico universal para conexiones de solo lectura a MariaDB/MySQL y PostgreSQL."""

import asyncio
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import aiomysql
import asyncpg
from app.domain.interfaces import RelationalDbInterface


class DynamicDBAdapter(RelationalDbInterface):
    """Conecta dinámicamente a bases de datos MariaDB/MySQL o PostgreSQL para introspección y consultas SELECT."""

    def __init__(
        self,
        engine: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str = "",
        timeout: float = 5.0
    ):
        self.engine = engine.lower().strip()
        self.host = host.strip()
        self.port = int(port)
        self.db = database_name.strip()
        self.user = username.strip()
        self.password = password or ""
        self.timeout = timeout

    @property
    def is_postgres(self) -> bool:
        return self.engine in ("postgresql", "postgres", "pgsql")

    @property
    def sqlglot_dialect(self) -> str:
        return "postgres" if self.is_postgres else "mysql"

    async def test_connection(self) -> Dict[str, Any]:
        """Verifica la conexión, obtiene versión del motor, cantidad total de tablas accesibles y esquemas detectados."""
        start = time.time()
        tables = await self.introspect_schema()
        latency_ms = int((time.time() - start) * 1000)

        schemas_map: Dict[str, int] = {}
        for t in tables:
            s_name = t.get("schema_name") or ("public" if self.is_postgres else (self.db or "default"))
            schemas_map[s_name] = schemas_map.get(s_name, 0) + 1

        schemas_detected = [
            {"name": s, "tables_count": count}
            for s, count in sorted(schemas_map.items(), key=lambda x: x[0].lower())
        ]

        return {
            "connected": True,
            "engine": "postgresql" if self.is_postgres else "mariadb",
            "host": self.host,
            "port": self.port,
            "database_name": self.db,
            "tables_detected": len(tables),
            "schemas_detected": schemas_detected,
            "latency_ms": latency_ms
        }

    async def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Ejecuta una consulta SELECT en el motor correspondiente y normaliza los tipos de retorno."""
        if self.is_postgres:
            return await self._execute_postgres_query(sql)
        return await self._execute_mysql_query(sql)

    async def introspect_schema(self) -> List[Dict[str, Any]]:
        """Extrae todas las tablas y columnas accesibles de la base de datos conectada."""
        if self.is_postgres:
            return await self._introspect_postgres()
        return await self._introspect_mysql()

    async def _execute_mysql_query(self, sql: str) -> List[Dict[str, Any]]:
        conn = await asyncio.wait_for(
            aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.db,
                cursorclass=aiomysql.DictCursor,
                autocommit=True
            ),
            timeout=self.timeout
        )
        try:
            async with conn.cursor() as cursor:
                await asyncio.wait_for(cursor.execute(sql), timeout=self.timeout)
                rows = await cursor.fetchall()
                return self._normalize_rows(rows)
        finally:
            conn.close()

    async def _execute_postgres_query(self, sql: str) -> List[Dict[str, Any]]:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db,
                timeout=self.timeout
            ),
            timeout=self.timeout
        )
        try:
            records = await asyncio.wait_for(conn.fetch(sql), timeout=self.timeout)
            dict_rows = [dict(r) for r in records]
            return self._normalize_rows(dict_rows)
        finally:
            await conn.close()

    async def _introspect_mysql(self) -> List[Dict[str, Any]]:
        conn = await asyncio.wait_for(
            aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.db,
                cursorclass=aiomysql.DictCursor,
                autocommit=True
            ),
            timeout=self.timeout
        )
        try:
            async with conn.cursor() as cursor:
                query = """
                SELECT 
                    TABLE_NAME as table_name,
                    COLUMN_NAME as column_name,
                    DATA_TYPE as data_type,
                    IS_NULLABLE as is_nullable,
                    COLUMN_COMMENT as column_comment
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME, ORDINAL_POSITION;
                """
                await cursor.execute(query, (self.db,))
                rows = await cursor.fetchall()

                fk_rows: List[Dict[str, Any]] = []
                try:
                    fk_query = """
                    SELECT
                        TABLE_NAME as table_name,
                        COLUMN_NAME as column_name,
                        REFERENCED_TABLE_NAME as referenced_table_name,
                        REFERENCED_COLUMN_NAME as referenced_column_name
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = %s
                      AND REFERENCED_TABLE_NAME IS NOT NULL;
                    """
                    await cursor.execute(fk_query, (self.db,))
                    fk_rows = await cursor.fetchall()
                except Exception:
                    fk_rows = []

                return self._group_columns_by_table(rows, fk_rows)
        finally:
            conn.close()

    async def _introspect_postgres(self) -> List[Dict[str, Any]]:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db,
                timeout=self.timeout
            ),
            timeout=self.timeout
        )
        try:
            query = """
            SELECT 
                c.table_schema,
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                COALESCE(pgd.description, '') as column_comment
            FROM information_schema.columns c
            LEFT JOIN pg_catalog.pg_statio_all_tables st
              ON c.table_schema = st.schemaname AND c.table_name = st.relname
            LEFT JOIN pg_catalog.pg_description pgd
              ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
            WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY c.table_schema, c.table_name, c.ordinal_position;
            """
            records = await conn.fetch(query)
            rows = [dict(r) for r in records]

            fk_rows: List[Dict[str, Any]] = []
            try:
                fk_query = """
                SELECT
                    kcu.table_schema AS table_schema,
                    kcu.table_name AS table_name,
                    kcu.column_name AS column_name,
                    ccu.table_schema AS referenced_table_schema,
                    ccu.table_name AS referenced_table_name,
                    ccu.column_name AS referenced_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast');
                """
                fk_records = await conn.fetch(fk_query)
                fk_rows = [dict(r) for r in fk_records]
            except Exception:
                fk_rows = []

            # Extraer índices definidos en PostgreSQL
            index_rows: List[Dict[str, Any]] = []
            try:
                idx_query = """
                SELECT
                    schemaname AS table_schema,
                    tablename AS table_name,
                    indexname AS index_name,
                    indexdef AS index_def
                FROM pg_catalog.pg_indexes
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast');
                """
                idx_records = await conn.fetch(idx_query)
                index_rows = [dict(r) for r in idx_records]
            except Exception:
                index_rows = []

            return self._group_columns_by_table(rows, fk_rows, index_rows)
        finally:
            await conn.close()

    @staticmethod
    def _candidate_entity_names(entity_token: str) -> Set[str]:
        """Genera variantes singulares/plurales en español e inglés para emparejar nombres de tablas."""
        tok = entity_token.lower().strip("_")
        if not tok:
            return set()
        variants = {tok, f"{tok}s", f"{tok}es"}
        if tok.endswith("es") and len(tok) > 3:
            variants.add(tok[:-2])
        if tok.endswith("s") and len(tok) > 2:
            variants.add(tok[:-1])
        if tok.endswith("y") and len(tok) > 2:
            variants.add(f"{tok[:-1]}ies")
        if tok.endswith("z") and len(tok) > 2:
            variants.add(f"{tok[:-1]}ces")
        return variants

    @staticmethod
    def _detect_descriptive_columns(columns: List[Dict[str, Any]]) -> List[str]:
        """
        Identifica cuáles son las columnas descriptivas humanas de una tabla
        (ej. nombre, razon_social, descripcion, titulo, estado, codigo) para usarlas
        al hacer JOIN en lugar de mostrar IDs numéricos en los gráficos.
        """
        priority_patterns = [
            r"\b(nombre|name|razon_social|denominacion|alias)\b",
            r"\b(descripcion|description|titulo|title|detalle|etiqueta|label)\b",
            r"\b(codigo|code|clave|sku|referencia|sigla)\b",
            r"\b(estado|status|tipo|type|categoria|category|departamento|proceso)\b",
        ]
        found: List[str] = []
        for pat in priority_patterns:
            for c in columns:
                c_name = c["name"]
                if c_name not in found and re.search(pat, c_name.lower().replace("_", " ")):
                    found.append(c_name)

        if not found:
            for c in columns:
                c_name = c["name"]
                c_type = str(c.get("type", "")).lower()
                if any(t in c_type for t in ("char", "text", "varchar", "enum", "string")):
                    if not c_name.lower().startswith("id") and not c_name.lower().endswith("_id"):
                        found.append(c_name)

        return found[:4]

    @classmethod
    def _group_columns_by_table(
        cls,
        rows: List[Dict[str, Any]],
        fk_rows: Optional[List[Dict[str, Any]]] = None,
        index_rows: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        tables: Dict[str, List[Dict[str, Any]]] = {}
        table_schemas: Dict[str, str] = {}
        for r in rows:
            schema_name = r.get("table_schema") or "public"
            raw_table = r["table_name"]
            # Para MySQL/MariaDB schema_name no aplica o es default; para Postgres usamos calificación si no es public
            full_table = f"{schema_name}.{raw_table}" if schema_name not in ("public", "default") else raw_table
            t_name = full_table
            table_schemas[t_name] = schema_name

            if t_name not in tables:
                tables[t_name] = []
            tables[t_name].append({
                "name": r["column_name"],
                "type": r["data_type"],
                "nullable": str(r.get("is_nullable", "")).upper() == "YES",
                "comment": r.get("column_comment") or ""
            })

        # Mapa de nombres en minúscula -> nombre real de tabla
        lower_to_real: Dict[str, str] = {k.lower(): k for k in tables.keys()}
        # También mapear sin prefijos comunes (ej. tbl_empresa -> empresa)
        stripped_to_real: Dict[str, str] = {}
        for real_name in tables.keys():
            low = real_name.lower()
            stripped = re.sub(r"^(tbl_|tb_|cat_|mae_|dim_|cfg_)", "", low)
            stripped_to_real[stripped] = real_name

        # Columnas descriptivas y llave primaria probable de cada tabla
        table_descriptive_cols: Dict[str, List[str]] = {}
        table_pk_col: Dict[str, str] = {}
        for t_name, cols in tables.items():
            table_descriptive_cols[t_name] = cls._detect_descriptive_columns(cols)
            col_names_lower = {c["name"].lower(): c["name"] for c in cols}
            t_low = t_name.lower()
            t_singular = t_low[:-1] if t_low.endswith("s") else t_low
            if "id" in col_names_lower:
                table_pk_col[t_name] = col_names_lower["id"]
            elif f"id_{t_low}" in col_names_lower:
                table_pk_col[t_name] = col_names_lower[f"id_{t_low}"]
            elif f"id_{t_singular}" in col_names_lower:
                table_pk_col[t_name] = col_names_lower[f"id_{t_singular}"]
            elif f"{t_singular}_id" in col_names_lower:
                table_pk_col[t_name] = col_names_lower[f"{t_singular}_id"]
            else:
                table_pk_col[t_name] = cols[0]["name"] if cols else "id"

        # 1. Registrar llaves foráneas explícitas de INFORMATION_SCHEMA
        outgoing_fks: Dict[str, List[Dict[str, Any]]] = {k: [] for k in tables.keys()}
        seen_edges: Set[Tuple[str, str, str]] = set()

        for fk in (fk_rows or []):
            src_t = fk.get("table_name")
            src_col = fk.get("column_name")
            ref_t = fk.get("referenced_table_name")
            ref_col = fk.get("referenced_column_name")
            if src_t in tables and ref_t in tables and src_col and ref_col:
                edge_key = (src_t.lower(), src_col.lower(), ref_t.lower())
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    outgoing_fks[src_t].append({
                        "column": src_col,
                        "referenced_table": ref_t,
                        "referenced_column": ref_col,
                        "descriptive_columns": table_descriptive_cols.get(ref_t, []),
                        "relationship_type": "explicit_fk"
                    })

        # 2. Inferir relaciones heurísticas por convención de nombres (ej. usuario.id_empresa -> empresa.id)
        for src_t, cols in tables.items():
            src_pk = table_pk_col.get(src_t, "").lower()
            for c in cols:
                c_name = c["name"]
                c_low = c_name.lower()
                if c_low == src_pk or c_low == "id":
                    continue

                entity_token = None
                m_prefix = re.match(r"^(?:id|fk|cod|codigo|cve)_([a-z0-9_]+)$", c_low)
                m_suffix = re.match(r"^([a-z0-9_]+)_(?:id|fk|cod|codigo)$", c_low)
                if m_prefix:
                    entity_token = m_prefix.group(1)
                elif m_suffix:
                    entity_token = m_suffix.group(1)

                if not entity_token:
                    continue

                target_table = None
                for cand in cls._candidate_entity_names(entity_token):
                    if cand in lower_to_real and lower_to_real[cand] != src_t:
                        target_table = lower_to_real[cand]
                        break
                    if cand in stripped_to_real and stripped_to_real[cand] != src_t:
                        target_table = stripped_to_real[cand]
                        break

                if not target_table:
                    continue

                edge_key = (src_t.lower(), c_low, target_table.lower())
                if edge_key in seen_edges:
                    continue

                # Determinar la columna destino en la tabla maestra (ej. empresa.id o empresa.id_empresa)
                target_cols_map = {tc["name"].lower(): tc["name"] for tc in tables[target_table]}
                ref_col = table_pk_col.get(target_table, "id")
                if c_low in target_cols_map:
                    ref_col = target_cols_map[c_low]
                elif "id" in target_cols_map:
                    ref_col = target_cols_map["id"]

                seen_edges.add(edge_key)
                outgoing_fks[src_t].append({
                    "column": c_name,
                    "referenced_table": target_table,
                    "referenced_column": ref_col,
                    "descriptive_columns": table_descriptive_cols.get(target_table, []),
                    "relationship_type": "inferred_fk"
                })

        # 3. Construir relaciones inversas (referenced_by) y lista consolidada de tablas vecinas (1-Hop)
        incoming_refs: Dict[str, List[Dict[str, Any]]] = {k: [] for k in tables.keys()}
        for src_t, fk_list in outgoing_fks.items():
            for fk in fk_list:
                ref_t = fk["referenced_table"]
                if ref_t in incoming_refs:
                    incoming_refs[ref_t].append({
                        "source_table": src_t,
                        "source_column": fk["column"],
                        "target_column": fk["referenced_column"],
                        "source_descriptive_columns": table_descriptive_cols.get(src_t, [])
                    })

        # Mapa de índices agrupados por tabla
        table_indexes: Dict[str, List[Dict[str, Any]]] = {k: [] for k in tables.keys()}
        for idx in (index_rows or []):
            s_name = idx.get("table_schema") or "public"
            raw_t = idx.get("table_name")
            full_t = f"{s_name}.{raw_t}" if s_name not in ("public", "default") else raw_t
            matched_key = None
            if full_t in table_indexes:
                matched_key = full_t
            elif raw_t in table_indexes:
                matched_key = raw_t
            if matched_key:
                table_indexes[matched_key].append({
                    "name": idx.get("index_name") or "",
                    "definition": idx.get("index_def") or ""
                })

        result_tables: List[Dict[str, Any]] = []
        for t_name, cols in tables.items():
            fks = outgoing_fks.get(t_name, [])
            refs_by = incoming_refs.get(t_name, [])
            related_set: List[str] = []
            for fk in fks:
                if fk["referenced_table"] not in related_set:
                    related_set.append(fk["referenced_table"])
            for rb in refs_by:
                if rb["source_table"] not in related_set:
                    related_set.append(rb["source_table"])

            result_tables.append({
                "schema_name": table_schemas.get(t_name, "public"),
                "table_name": t_name,
                "primary_key": table_pk_col.get(t_name, "id"),
                "descriptive_columns": table_descriptive_cols.get(t_name, []),
                "columns_count": len(cols),
                "columns": cols,
                "foreign_keys": fks,
                "referenced_by": refs_by,
                "related_tables": related_set,
                "indexes": table_indexes.get(t_name, [])
            })

        return result_tables

    @staticmethod
    def _normalize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted_rows: List[Dict[str, Any]] = []
        for row in rows:
            clean_row: Dict[str, Any] = {}
            for k, v in row.items():
                if v is None or isinstance(v, (str, int, float, bool)):
                    clean_row[k] = v
                elif hasattr(v, "isoformat"):
                    clean_row[k] = v.isoformat()
                elif hasattr(v, "__float__"):
                    clean_row[k] = float(v)
                else:
                    clean_row[k] = str(v)
            formatted_rows.append(clean_row)
        return formatted_rows
