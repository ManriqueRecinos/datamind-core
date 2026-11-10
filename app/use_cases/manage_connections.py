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
        set_active: bool = True,
        selected_schemas: Optional[List[str]] = None
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
            synced_tables=[],
            selected_schemas=selected_schemas or []
        )
        self.session.add(conn_model)
        await self.session.commit()
        await self.session.refresh(conn_model)

        serialized = self._serialize_connection(conn_model)
        serialized["tables_detected"] = test_info["tables_detected"]
        serialized["latency_ms"] = test_info["latency_ms"]
        serialized["schemas_detected"] = test_info.get("schemas_detected", [])
        return serialized

    async def update_connection(
        self,
        connection_id: str,
        name: Optional[str] = None,
        engine: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database_name: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        selected_schemas: Optional[List[str]] = None,
        set_active: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Actualiza la configuración, credenciales o esquemas seleccionados de una conexión."""
        conn_uuid = uuid.UUID(str(connection_id))
        target = await self.session.get(DatabaseConnectionModel, conn_uuid)
        if not target:
            raise ValueError(f"No se encontró la conexión con ID {connection_id}")

        if name is not None:
            target.name = name.strip()
        if engine is not None:
            target.engine = "postgresql" if engine.lower() in ("postgresql", "postgres", "pgsql") else "mariadb"
        if host is not None:
            target.host = host.strip()
        if port is not None:
            target.port = int(port)
        if database_name is not None:
            target.database_name = database_name.strip()
        if username is not None:
            target.username = username.strip()
        if password is not None and password != "":
            target.password = password
        if selected_schemas is not None:
            target.selected_schemas = selected_schemas

        if set_active is True:
            await self.session.execute(
                update(DatabaseConnectionModel).values(is_active=False)
            )
            target.is_active = True

        await self.session.commit()
        await self.session.refresh(target)
        return self._serialize_connection(target)

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
        allowed_schemas = set(s.lower() for s in (conn_model.selected_schemas or [])) if conn_model.selected_schemas else None

        enriched_tables = []
        for t in all_tables:
            s_name = t.get("schema_name") or "public"
            if allowed_schemas is not None and s_name.lower() not in allowed_schemas:
                continue

            t_name = t["table_name"]
            fks = t.get("foreign_keys", [])
            refs_by = t.get("referenced_by", [])
            related_tables = t.get("related_tables", [])

            enriched_tables.append({
                "schema_name": s_name,
                "table_name": t_name,
                "primary_key": t.get("primary_key", "id"),
                "descriptive_columns": t.get("descriptive_columns", []),
                "columns_count": t["columns_count"],
                "columns": t["columns"],
                "foreign_keys": fks,
                "referenced_by": refs_by,
                "related_tables": related_tables,
                "indexes": t.get("indexes", []),
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

    @staticmethod
    def build_relational_schema_embedding_text(
        conn_name: str,
        engine_label: str,
        database_name: str,
        table: Dict[str, Any]
    ) -> tuple[str, List[str]]:
        """
        Construye el documento semántico enriquecido para pgvector siguiendo las prácticas de
        `embedding-strategies` y `rag-engineer`: incluye clasificación de columnas, llaves foráneas,
        columnas descriptivas de las tablas relacionadas y reglas explícitas de JOIN.
        """
        t_name = table["table_name"]
        pk_col = table.get("primary_key", "id")
        desc_cols = table.get("descriptive_columns", [])
        fks = table.get("foreign_keys", [])
        refs_by = table.get("referenced_by", [])

        columns_desc = ", ".join(
            [
                f"{col['name']} ({col['type']}" + (f", nota: '{col['comment']}'" if col.get("comment") else "") + ")"
                for col in table.get("columns", [])
            ]
        )
        desc_cols_str = ", ".join([f"`{c}`" for c in desc_cols]) if desc_cols else "ninguna"

        join_hints: List[str] = []
        fk_lines: List[str] = []
        for fk in fks:
            src_col = fk["column"]
            ref_t = fk["referenced_table"]
            ref_col = fk["referenced_column"]
            target_labels = fk.get("descriptive_columns") or []
            labels_str = ", ".join([f"`{ref_t}.{lbl}`" for lbl in target_labels[:3]]) if target_labels else f"`{ref_t}.*`"
            join_sql = f"JOIN {ref_t} ON {t_name}.{src_col} = {ref_t}.{ref_col}"
            join_hints.append(f"{join_sql} (columnas descriptivas de {ref_t}: {', '.join(target_labels[:3]) or ref_col})")
            fk_lines.append(
                f"  - La columna llave foránea `{t_name}.{src_col}` referencia a `{ref_t}.{ref_col}`. "
                f"IMPORTANTE: `{src_col}` solo contiene el ID de relación; para obtener el nombre o datos reales de `{ref_t}` "
                f"en consultas o gráficos SIEMPRE haz `{join_sql}` y selecciona {labels_str} en lugar de `{src_col}`."
            )

        incoming_lines: List[str] = []
        for rb in refs_by[:8]:
            s_t = rb["source_table"]
            s_col = rb["source_column"]
            t_col = rb["target_column"]
            join_sql = f"JOIN {s_t} ON {t_name}.{t_col} = {s_t}.{s_col}"
            join_hints.append(join_sql)
            incoming_lines.append(
                f"  - La tabla `{s_t}` se vincula con `{t_name}` mediante `{s_t}.{s_col} = {t_name}.{t_col}` (`{join_sql}`)."
            )

        relations_block = ""
        if fk_lines or incoming_lines:
            relations_block = "\nRELACIONES Y JOINS APRENDIDOS ENTRE TABLAS:\n"
            if fk_lines:
                relations_block += "\n".join(fk_lines) + "\n"
            if incoming_lines:
                relations_block += "\n".join(incoming_lines) + "\n"

        content = (
            f"Conexión: {conn_name} | Motor: {engine_label} | Base de datos: `{database_name}`.\n"
            f"Tabla: `{t_name}` (Llave primaria: `{pk_col}` | Columnas descriptivas/etiquetas: {desc_cols_str}).\n"
            f"Columnas disponibles ({len(table.get('columns', []))}): {columns_desc}."
            f"{relations_block}"
            f"Usa esta tabla y sus relaciones JOIN para consultas SQL y gráficos exactos sobre `{t_name}` en `{database_name}`."
        )
        return content, join_hints

    async def vectorize_selected_tables(
        self,
        connection_id: str,
        selected_tables: List[str]
    ) -> Dict[str, Any]:
        """Vectoriza en pgvector únicamente las tablas elegidas por el usuario junto con su grafo de relaciones."""
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
            s_name = table.get("schema_name") or ("public" if adapter.is_postgres else "default")
            content, join_hints = self.build_relational_schema_embedding_text(
                conn_name=conn_model.name,
                engine_label=engine_label,
                database_name=conn_model.database_name,
                table=table
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
                    "schema_name": s_name,
                    "table_name": t_name,
                    "primary_key": table.get("primary_key", "id"),
                    "descriptive_columns": table.get("descriptive_columns", []),
                    "related_tables": table.get("related_tables", []),
                    "join_hints": join_hints,
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
        selected_schemas = list(conn.selected_schemas or []) if conn.selected_schemas else None
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
            "selected_schemas": selected_schemas,
            "created_at": conn.created_at.isoformat() if conn.created_at else None
        }
