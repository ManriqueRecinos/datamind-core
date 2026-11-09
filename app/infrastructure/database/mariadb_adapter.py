"""Adaptador asíncrono de solo lectura para la base de datos externa MariaDB."""

import asyncio
from typing import Any, Dict, List
import aiomysql
from app.core.config import get_settings
from app.domain.interfaces import RelationalDbInterface


class MariaDBAdapter(RelationalDbInterface):
    """Maneja conexiones asíncronas a MariaDB para Text-to-SQL e introspección de esquemas."""

    def __init__(self):
        settings = get_settings()
        self.host = settings.mariadb_host
        self.port = settings.mariadb_port
        self.user = settings.mariadb_user
        self.password = settings.mariadb_password
        self.db = settings.mariadb_db
        self.timeout = settings.mariadb_timeout_seconds

    async def _get_connection(self) -> aiomysql.Connection:
        """Crea una conexión asíncrona a MariaDB con timeout estricto."""
        return await asyncio.wait_for(
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

    async def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Ejecuta una consulta SQL SELECT y retorna las filas como lista de diccionarios."""
        conn = await self._get_connection()
        try:
            async with conn.cursor() as cursor:
                await asyncio.wait_for(cursor.execute(sql), timeout=self.timeout)
                rows = await cursor.fetchall()
                # Convertir tipos no serializables si es necesario (fechas, decimales)
                formatted_rows: List[Dict[str, Any]] = []
                for row in rows:
                    clean_row = {}
                    for k, v in row.items():
                        if hasattr(v, "isoformat"):
                            clean_row[k] = v.isoformat()
                        elif hasattr(v, "__float__"):
                            clean_row[k] = float(v)
                        else:
                            clean_row[k] = v
                    formatted_rows.append(clean_row)
                return formatted_rows
        finally:
            conn.close()

    async def introspect_schema(self) -> List[Dict[str, Any]]:
        """Extrae la lista de tablas y columnas accesibles en la base de datos."""
        conn = await self._get_connection()
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

                tables: Dict[str, List[Dict[str, Any]]] = {}
                for r in rows:
                    t_name = r["table_name"]
                    if t_name not in tables:
                        tables[t_name] = []
                    tables[t_name].append({
                        "name": r["column_name"],
                        "type": r["data_type"],
                        "nullable": r["is_nullable"] == "YES",
                        "comment": r.get("column_comment", "")
                    })

                return [{"table_name": k, "columns": v} for k, v in tables.items()]
        finally:
            conn.close()
