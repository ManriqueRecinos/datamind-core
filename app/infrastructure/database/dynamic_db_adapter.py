"""Adaptador dinámico universal para conexiones de solo lectura a MariaDB/MySQL y PostgreSQL."""

import asyncio
import time
from typing import Any, Dict, List
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
        """Verifica la conexión, obtiene versión del motor y cantidad total de tablas accesibles."""
        start = time.time()
        tables = await self.introspect_schema()
        latency_ms = int((time.time() - start) * 1000)
        return {
            "connected": True,
            "engine": "postgresql" if self.is_postgres else "mariadb",
            "host": self.host,
            "port": self.port,
            "database_name": self.db,
            "tables_detected": len(tables),
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
                return self._group_columns_by_table(rows)
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
                table_name,
                column_name,
                data_type,
                is_nullable,
                '' as column_comment
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
            """
            records = await conn.fetch(query)
            rows = [dict(r) for r in records]
            return self._group_columns_by_table(rows)
        finally:
            await conn.close()

    @staticmethod
    def _group_columns_by_table(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tables: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            t_name = r["table_name"]
            if t_name not in tables:
                tables[t_name] = []
            tables[t_name].append({
                "name": r["column_name"],
                "type": r["data_type"],
                "nullable": str(r.get("is_nullable", "")).upper() == "YES",
                "comment": r.get("column_comment") or ""
            })
        return [
            {
                "table_name": k,
                "columns_count": len(v),
                "columns": v
            }
            for k, v in tables.items()
        ]

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
