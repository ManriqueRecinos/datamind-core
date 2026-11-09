"""Caso de uso para gestionar conexiones dinámicas a bases de datos e indexar tablas selectivamente."""

from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.infrastructure.database.dynamic_db_adapter import DynamicDBAdapter
from app.infrastructure.database.models import (
    DatabaseConnectionModel,
    KnowledgeDocumentModel,
)
from app.infrastructure.database.vector_repository import VectorRepository
from app.use_cases.ingest_knowledge import IngestKnowledgeUseCase


class ManageConnectionsUseCase:
    """Orquesta el registro de bases de datos, test de conexión, exploración de tablas y vectorización."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.vector_repo = VectorRepository(session)
        self.ingest_use_case = IngestKnowledgeUseCase(session)
        self.settings = get_settings()

    async def ensure_default_connection(self) -> Optional[DatabaseConnectionModel]:
        """Si no existen conexiones registradas, crea la conexión por defecto desde .env (si está configurada)."""
        stmt = select(DatabaseConnectionModel).order_by(DatabaseConnectionModel.created_at.asc())
        res = await self.session.execute(stmt)
        existing = res.scalars().all()
        if existing:
            return next((c for c in existing if c.is_active), existing[0])

        if not self.settings.mariadb_host or not self.settings.mariadb_db:
            return None

        # Detectar tablas previamente sincronizadas sin connection_id
        doc_stmt = select(KnowledgeDocumentModel).filter(KnowledgeDocumentModel.category == "db_schema")
        doc_res = await self.session.execute(doc_stmt)
        docs = doc_res.scalars().all()
        initial_tables = []
        for d in docs:
            t_name = (d.metadata_ or {}).get("table_name")
            if t_name and t_name not in initial_tables:
                initial_tables.append(t_name)

        default_conn = DatabaseConnectionModel(
            name=f"MariaDB ({self.settings.mariadb_db})",
            engine="mariadb",
            host=self.settings.mariadb_host,
            port=self.settings.mariadb_port,
            database_name=self.settings.mariadb_db,
            username=self.settings.mariadb_user,
            password=self.settings.mariadb_password,
            is_active=True,
            synced_tables=initial_tables
        )
        self.session.add(default_conn)
        await self.session.commit()
        await self.session.refresh(default_conn)

        # Vincular documentos huérfanos a esta conexión por defecto
        if docs:
            for d in docs:
                meta = dict(d.metadata_ or {})
                if "connection_id" not in meta:
                    meta["connection_id"] = str(default_conn.id)
                    d.metadata_ = meta
            await self.session.commit()

        return default_conn

    async def test_credentials(
        self,
        engine: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str = ""
    ) -> Dict[str, Any]:
        """Prueba en vivo las credenciales proporcionadas y retorna estadísticas del esquema."""
        adapter = DynamicDBAdapter(
            engine=engine,
            host=host,
            port=port,
            database_name=database_name,
            username=username,
            password=password
        )
        return await adapter.test_connection()

    async def list_connections(self) -> List[Dict[str, Any]]:
        """Retorna todas las conexiones registradas (con contraseña enmascarada)."""
        await self.ensure_default_connection()
        stmt = select(DatabaseConnectionModel).order_by(
            DatabaseConnectionModel.is_active.desc(),
            DatabaseConnectionModel.created_at.desc()
        )
        res = await self.session.execute(stmt)
        items = res.scalars().all()
        return [self._serialize_connection(c) for c in items]

    async def create_connection(
        self,
        name: str,
        engine: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str = "",
        set_active: bool = True
    ) -> Dict[str, Any]:
        """Verifica y guarda una nueva conexión a base de datos."""
        norm_engine = "postgresql" if engine.lower() in ("postgresql", "postgres", "pgsql") else "mariadb"
        adapter = DynamicDBAdapter(
            engine=norm_engine,
            host=host,
            port=port,
            database_name=database_name,
            username=username,
            password=password
        )
        # Verificar conectividad antes de guardar
        test_info = await adapter.test_connection()

        if set_active:
            await self.session.execute(
                update(DatabaseConnectionModel).values(is_active=False)
            )

        conn_model = DatabaseConnectionModel(
            name=name.strip(),
            engine=norm_engine,
            host=host.strip(),
            port=int(port),
            database_name=database_name.strip(),
            username=username.strip(),
            password=password or "",
            is_active=set_active,
            synced_tables=[]
        )
        self.session.add(conn_model)
        await self.session.commit()
        await self.session.refresh(conn_model)

        serialized = self._serialize_connection(conn_model)
        serialized["tables_detected"] = test_info["tables_detected"]
        serialized["latency_ms"] = test_info["latency_ms"]
        return serialized

    async def activate_connection(self, connection_id: str) -> Dict[str, Any]:
        """Marca una conexión como la activa por defecto para el asistente de chat."""
        conn_uuid = uuid.UUID(str(connection_id))
        target = await self.session.get(DatabaseConnectionModel, conn_uuid)
        if not target:
            raise ValueError(f"No se encontró la conexión con ID {connection_id}")

        await self.session.execute(
            update(DatabaseConnectionModel).values(is_active=False)
        )
        target.is_active = True
        await self.session.commit()
        await self.session.refresh(target)
        return self._serialize_connection(target)

    async def delete_connection(self, connection_id: str) -> Dict[str, Any]:
        """Elimina una conexión y limpia sus vectores de esquema en pgvector."""
        conn_uuid = uuid.UUID(str(connection_id))
        target = await self.session.get(DatabaseConnectionModel, conn_uuid)
        if not target:
            raise ValueError(f"No se encontró la conexión con ID {connection_id}")

        deleted_docs = await self.vector_repo.delete_schema_documents(connection_id=str(conn_uuid))
        was_active = target.is_active
        await self.session.delete(target)
        await self.session.commit()

        # Si era la activa, activar la más reciente disponible
        if was_active:
            stmt = select(DatabaseConnectionModel).order_by(DatabaseConnectionModel.created_at.desc())
            res = await self.session.execute(stmt)
            first_remaining = res.scalars().first()
            if first_remaining:
                first_remaining.is_active = True
                await self.session.commit()

        return {
            "status": "deleted",
            "connection_id": str(conn_uuid),
            "vector_documents_removed": deleted_docs
        }

    async def get_connection_tables(self, connection_id: str) -> Dict[str, Any]:
        """Introspecciona todas las tablas de una conexión y marca cuáles ya están vectorizadas."""
        conn_uuid = uuid.UUID(str(connection_id))
        conn_model = await self.session.get(DatabaseConnectionModel, conn_uuid)
        if not conn_model:
            raise ValueError(f"No se encontró la conexión con ID {connection_id}")

        adapter = self._build_adapter(conn_model)
        all_tables = await adapter.introspect_schema()
        synced_set = {t.lower() for t in (conn_model.synced_tables or [])}

        enriched_tables = []
        for t in all_tables:
            t_name = t["table_name"]
            enriched_tables.append({
                "table_name": t_name,
                "columns_count": t["columns_count"],
                "columns": t["columns"],
                "column_names_preview": ", ".join([c["name"] for c in t["columns"][:8]])
                + (f" (+{len(t['columns']) - 8} más)" if len(t["columns"]) > 8 else ""),
                "is_vectorized": t_name.lower() in synced_set
            })

        return {
            "connection": self._serialize_connection(conn_model),
            "total_tables": len(enriched_tables),
            "vectorized_count": len(synced_set),
            "tables": enriched_tables
        }

    async def vectorize_selected_tables(
        self,
        connection_id: str,
        selected_tables: List[str]
    ) -> Dict[str, Any]:
        """Vectoriza en pgvector únicamente las tablas elegidas por el usuario para esa conexión."""
        if not selected_tables:
            raise ValueError("Debe seleccionar al menos una tabla para vectorizar.")

        conn_uuid = uuid.UUID(str(connection_id))
        conn_model = await self.session.get(DatabaseConnectionModel, conn_uuid)
        if not conn_model:
            raise ValueError(f"No se encontró la conexión con ID {connection_id}")

        adapter = self._build_adapter(conn_model)
        all_tables = await adapter.introspect_schema()
        wanted_lower = {t.strip().lower() for t in selected_tables if t.strip()}
        matched_tables = [t for t in all_tables if t["table_name"].lower() in wanted_lower]

        if not matched_tables:
            raise ValueError("Ninguna de las tablas seleccionadas fue encontrada en la base de datos.")

        # Eliminar vectores previos de estas mismas tablas para evitar duplicados (idempotencia)
        matched_names = [t["table_name"] for t in matched_tables]
        await self.vector_repo.delete_schema_documents(
            connection_id=str(conn_model.id),
            table_names=matched_names
        )

        newly_synced: List[str] = []
        engine_label = "PostgreSQL" if adapter.is_postgres else "MariaDB/MySQL"

        for table in matched_tables:
            t_name = table["table_name"]
            columns_desc = ", ".join(
                [f"{col['name']} ({col['type']})" for col in table["columns"]]
            )
            content = (
                f"Conexión: {conn_model.name} | Motor: {engine_label} | Base de datos: `{conn_model.database_name}`.\n"
                f"Tabla: `{t_name}`.\n"
                f"Columnas disponibles ({len(table['columns'])}): {columns_desc}.\n"
                f"Usa esta tabla para consultas SQL sobre `{t_name}` en `{conn_model.database_name}`."
            )

            await self.ingest_use_case.execute(
                title=f"[{conn_model.database_name}] Esquema de Tabla: {t_name}",
                category="db_schema",
                department=conn_model.name,
                content=content,
                metadata={
                    "connection_id": str(conn_model.id),
                    "connection_name": conn_model.name,
                    "engine": conn_model.engine,
                    "database_name": conn_model.database_name,
                    "table_name": t_name,
                    "columns_count": len(table["columns"])
                }
            )
            newly_synced.append(t_name)

        # Actualizar registro de tablas sincronizadas en la conexión
        existing_synced = list(conn_model.synced_tables or [])
        existing_lower = {x.lower() for x in existing_synced}
        for name in newly_synced:
            if name.lower() not in existing_lower:
                existing_synced.append(name)
                existing_lower.add(name.lower())

        conn_model.synced_tables = existing_synced
        await self.session.commit()
        await self.session.refresh(conn_model)

        return {
            "status": "vectorized",
            "connection_id": str(conn_model.id),
            "connection_name": conn_model.name,
            "database_name": conn_model.database_name,
            "engine": conn_model.engine,
            "tables_vectorized_now": len(newly_synced),
            "tables": newly_synced,
            "total_synced_tables": len(conn_model.synced_tables or [])
        }

    async def get_active_or_target_connection(
        self, connection_id: Optional[str] = None
    ) -> Optional[DatabaseConnectionModel]:
        """Obtiene la conexión solicitada o la conexión activa por defecto."""
        await self.ensure_default_connection()
        if connection_id:
            try:
                conn_uuid = uuid.UUID(str(connection_id))
                found = await self.session.get(DatabaseConnectionModel, conn_uuid)
                if found:
                    return found
            except Exception:
                pass

        stmt = select(DatabaseConnectionModel).filter(DatabaseConnectionModel.is_active.is_(True))
        res = await self.session.execute(stmt)
        active = res.scalars().first()
        if active:
            return active

        stmt_any = select(DatabaseConnectionModel).order_by(DatabaseConnectionModel.created_at.desc())
        res_any = await self.session.execute(stmt_any)
        return res_any.scalars().first()

    @staticmethod
    def _build_adapter(conn_model: DatabaseConnectionModel) -> DynamicDBAdapter:
        return DynamicDBAdapter(
            engine=conn_model.engine,
            host=conn_model.host,
            port=conn_model.port,
            database_name=conn_model.database_name,
            username=conn_model.username,
            password=conn_model.password
        )

    @staticmethod
    def _serialize_connection(conn: DatabaseConnectionModel) -> Dict[str, Any]:
        synced = list(conn.synced_tables or [])
        return {
            "id": str(conn.id),
            "name": conn.name,
            "engine": conn.engine,
            "host": conn.host,
            "port": conn.port,
            "database_name": conn.database_name,
            "username": conn.username,
            "password_masked": "********" if conn.password else "",
            "is_active": bool(conn.is_active),
            "synced_tables": synced,
            "synced_tables_count": len(synced),
            "created_at": conn.created_at.isoformat() if conn.created_at else None
        }
