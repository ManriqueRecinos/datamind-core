"""Caso de uso para sincronizar y vectorizar el esquema de MariaDB en pgvector."""

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.mariadb_adapter import MariaDBAdapter
from app.use_cases.ingest_knowledge import IngestKnowledgeUseCase


class SyncSchemaUseCase:
    """Introspecciona las tablas de MariaDB y las indexa como conocimiento para Text-to-SQL."""

    def __init__(self, session: AsyncSession, mariadb: Optional[MariaDBAdapter] = None):
        self.session = session
        self.mariadb = mariadb or MariaDBAdapter()
        self.ingest_use_case = IngestKnowledgeUseCase(session)

    async def execute(self, table_filter: Optional[List[str]] = None) -> Dict[str, Any]:
        """Extrae el catálogo de MariaDB y crea fragmentos vectorizados por cada tabla."""
        all_tables = await self.mariadb.introspect_schema()
        
        if table_filter:
            filter_lower = [t.lower() for t in table_filter]
            tables = [t for t in all_tables if t["table_name"].lower() in filter_lower]
        else:
            tables = all_tables

        synced_tables: List[str] = []

        for table in tables:
            t_name = table["table_name"]
            columns_desc = ", ".join(
                [f"{col['name']} ({col['type']})" for col in table["columns"]]
            )
            content = (
                f"Tabla de base de datos MariaDB: `{t_name}`.\n"
                f"Columnas disponibles: {columns_desc}.\n"
                f"Esta tabla almacena registros operacionales para el sistema de procesos."
            )

            await self.ingest_use_case.execute(
                title=f"Esquema de Tabla: {t_name}",
                category="db_schema",
                department="Sistemas",
                content=content,
                metadata={"table_name": t_name, "columns_count": len(table["columns"])}
            )
            synced_tables.append(t_name)

        return {
            "status": "synchronized",
            "database": self.mariadb.db,
            "tables_indexed": len(synced_tables),
            "tables": synced_tables
        }
