"""Repositorio para almacenamiento y búsqueda por similitud en PostgreSQL con pgvector."""

from typing import Any, Dict, List, Optional, Set
import re
import uuid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities import DocumentChunk
from app.infrastructure.database.models import (
    KnowledgeDocumentModel,
    KnowledgeVectorChunkModel,
)
from app.use_cases.intent_classifier import remove_accents


class VectorRepository:
    """Implementa operaciones de persistencia y búsqueda vectorial usando pgvector."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(
        self,
        title: str,
        category: str,
        department: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> KnowledgeDocumentModel:
        """Crea el registro maestro del documento."""
        doc = KnowledgeDocumentModel(
            title=title,
            category=category,
            department=department,
            content=content,
            metadata_=metadata or {}
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def save_chunks(
        self, document_id: uuid.UUID, chunks: List[DocumentChunk]
    ) -> List[KnowledgeVectorChunkModel]:
        """Inserta los fragmentos vectorizados asociados al documento."""
        chunk_models = []
        for idx, chunk in enumerate(chunks):
            chunk_model = KnowledgeVectorChunkModel(
                document_id=document_id,
                chunk_index=idx,
                chunk_text=chunk.chunk_text,
                embedding=chunk.embedding,
                metadata_=chunk.metadata
            )
            chunk_models.append(chunk_model)
            self.session.add(chunk_model)

        await self.session.commit()
        return chunk_models

    async def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 4,
        category: Optional[str] = None,
        connection_id: Optional[str] = None
    ) -> List[DocumentChunk]:
        """Realiza búsqueda semántica por distancia coseno usando el índice HNSW de pgvector."""
        # En pgvector, cosine_distance genera la distancia (menor es más similar)
        distance = KnowledgeVectorChunkModel.embedding.cosine_distance(query_embedding)
        query = select(
            KnowledgeVectorChunkModel,
            distance.label("distance")
        ).order_by(distance).limit(top_k)

        if category or connection_id:
            query = query.join(KnowledgeDocumentModel)
            if category:
                query = query.filter(KnowledgeDocumentModel.category == category)
            if connection_id:
                query = query.filter(
                    KnowledgeDocumentModel.metadata_["connection_id"].astext == str(connection_id)
                )

        result = await self.session.execute(query)
        rows = result.all()

        results: List[DocumentChunk] = []
        for row in rows:
            chunk_model = row[0]
            dist = float(row[1])
            # Similitud coseno normalizada: 1.0 - distancia
            similarity = round(max(0.0, 1.0 - dist), 4)

            results.append(
                DocumentChunk(
                    id=str(chunk_model.id),
                    document_id=str(chunk_model.document_id),
                    chunk_index=chunk_model.chunk_index,
                    chunk_text=chunk_model.chunk_text,
                    metadata=chunk_model.metadata_ or {},
                    similarity_score=similarity
                )
            )

        return results

    async def search_schema_with_relations(
        self,
        query_embedding: List[float],
        prompt_text: str,
        top_k: int = 6,
        connection_id: Optional[str] = None
    ) -> List[DocumentChunk]:
        """
        Búsqueda Híbrida + Expansión Automática de Vecinos (1-Hop Relational Graph Expansion)
        siguiendo las skills `rag-engineer` y `hybrid-search-implementation`:
        1. Recupera los esquemas más similares por vector (pgvector HNSW).
        2. Combina coincidencia léxica de nombres de tablas/entidades mencionados en el prompt.
        3. Lee `metadata["related_tables"]` de las tablas recuperadas y trae automáticamente los
           esquemas de las tablas relacionadas (ej. si entra `usuario`, trae también `empresa` para el JOIN).
        """
        primary_chunks = await self.search_similar(
            query_embedding=query_embedding,
            top_k=top_k,
            category="db_schema",
            connection_id=connection_id
        )
        if not primary_chunks and connection_id:
            primary_chunks = await self.search_similar(
                query_embedding=query_embedding,
                top_k=top_k,
                category="db_schema"
            )

        collected_by_id: Dict[str, DocumentChunk] = {}
        seen_tables: Set[str] = set()
        neighbor_tables_to_fetch: Set[str] = set()

        for ch in primary_chunks:
            collected_by_id[ch.id] = ch
            t_name = str((ch.metadata or {}).get("table_name", "")).strip()
            if t_name:
                seen_tables.add(t_name.lower())
            for rel_t in (ch.metadata or {}).get("related_tables", []) or []:
                if rel_t and str(rel_t).strip().lower() not in seen_tables:
                    neighbor_tables_to_fetch.add(str(rel_t).strip())

        # Paso 2 (Hybrid Search): Buscar todos los documentos de esquema de la conexión para:
        # a) Coincidencia léxica directa con palabras del prompt (ej. "usuario", "empresa", "rollo")
        # b) Expansión 1-Hop de las tablas vecinas (`related_tables`)
        stmt = (
            select(KnowledgeVectorChunkModel, KnowledgeDocumentModel)
            .join(KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id)
            .where(KnowledgeDocumentModel.category == "db_schema")
        )
        if connection_id:
            stmt = stmt.where(
                KnowledgeDocumentModel.metadata_["connection_id"].astext == str(connection_id)
            )

        all_schema_rows = (await self.session.execute(stmt)).all()

        # Si el número total de tablas de esquema sincronizadas para esta conexión es compacto (<= 15 tablas),
        # inyectamos todos los esquemas para garantizar que las consultas relacionales multi-tabla (RBAC, joins
        # complejos de 5+ tablas) dispongan del grafo 100% completo sin omisión de tablas puente.
        unique_table_count = len({str((cm.metadata_ or dm.metadata_ or {}).get("table_name", "")).lower() for cm, dm in all_schema_rows if (cm.metadata_ or dm.metadata_ or {}).get("table_name")})
        if 0 < unique_table_count <= 15:
            full_schema_chunks = []
            for chunk_model, doc_model in all_schema_rows:
                meta = chunk_model.metadata_ or doc_model.metadata_ or {}
                full_schema_chunks.append(DocumentChunk(
                    id=str(chunk_model.id),
                    document_id=str(chunk_model.document_id),
                    chunk_index=chunk_model.chunk_index,
                    chunk_text=chunk_model.chunk_text,
                    metadata=meta,
                    similarity_score=0.98
                ))
            return full_schema_chunks

        norm_prompt = remove_accents((prompt_text or "").lower())

        # Primera pasada: coincidencias léxicas directas en el prompt
        for chunk_model, doc_model in all_schema_rows:
            c_id = str(chunk_model.id)
            if c_id in collected_by_id:
                continue
            meta = chunk_model.metadata_ or doc_model.metadata_ or {}
            t_name = str(meta.get("table_name", "")).strip()
            if not t_name:
                continue
            t_norm = remove_accents(t_name.lower())
            t_singular = t_norm[:-1] if t_norm.endswith("s") and len(t_norm) > 3 else t_norm
            t_clean = re.sub(r"^(tbl_|tb_|cat_|mae_|dim_)", "", t_singular)

            if (
                (len(t_norm) >= 3 and re.search(rf"\b{re.escape(t_norm)}\b", norm_prompt))
                or (len(t_clean) >= 3 and re.search(rf"\b{re.escape(t_clean)}\b", norm_prompt))
            ):
                collected_by_id[c_id] = DocumentChunk(
                    id=c_id,
                    document_id=str(chunk_model.document_id),
                    chunk_index=chunk_model.chunk_index,
                    chunk_text=chunk_model.chunk_text,
                    metadata=meta,
                    similarity_score=0.95
                )
                seen_tables.add(t_name.lower())
                for rel_t in meta.get("related_tables", []) or []:
                    if rel_t and str(rel_t).strip().lower() not in seen_tables:
                        neighbor_tables_to_fetch.add(str(rel_t).strip())

        # Segunda pasada (1-Hop Relational Graph Expansion): traer tablas relacionadas por FK
        neighbor_lower = {n.lower() for n in neighbor_tables_to_fetch}
        if neighbor_lower:
            for chunk_model, doc_model in all_schema_rows:
                c_id = str(chunk_model.id)
                if c_id in collected_by_id:
                    continue
                meta = chunk_model.metadata_ or doc_model.metadata_ or {}
                t_name = str(meta.get("table_name", "")).strip()
                if t_name and t_name.lower() in neighbor_lower:
                    collected_by_id[c_id] = DocumentChunk(
                        id=c_id,
                        document_id=str(chunk_model.document_id),
                        chunk_index=chunk_model.chunk_index,
                        chunk_text=chunk_model.chunk_text,
                        metadata=meta,
                        similarity_score=0.88
                    )
                    seen_tables.add(t_name.lower())

        return list(collected_by_id.values())[:max(top_k + 4, 10)]

    async def delete_schema_documents(
        self,
        connection_id: str,
        table_names: Optional[List[str]] = None
    ) -> int:
        """Elimina documentos de esquema previos de una conexión (o tablas específicas) para evitar duplicados."""
        stmt = select(KnowledgeDocumentModel.id).filter(
            KnowledgeDocumentModel.category == "db_schema",
            KnowledgeDocumentModel.metadata_["connection_id"].astext == str(connection_id)
        )
        if table_names:
            stmt = stmt.filter(
                KnowledgeDocumentModel.metadata_["table_name"].astext.in_(table_names)
            )
        res = await self.session.execute(stmt)
        doc_ids = [r[0] for r in res.all()]
        if not doc_ids:
            return 0

        await self.session.execute(
            delete(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id.in_(doc_ids))
        )
        await self.session.commit()
        return len(doc_ids)

    async def search_learned_rules(
        self,
        query_embedding: List[float],
        prompt_text: str,
        top_k: int = 5,
        connection_id: Optional[str] = None
    ) -> List[DocumentChunk]:
        """
        Recupera las cápsulas de entrenamiento enseñadas por el usuario
        (`custom_relation`, `business_rule`, `kpi_formula`, `sql_example`) combinando
        similitud vectorial en pgvector + coincidencia léxica de tablas mencionadas.
        """
        learned_categories = ["custom_relation", "business_rule", "kpi_formula", "sql_example"]
        distance = KnowledgeVectorChunkModel.embedding.cosine_distance(query_embedding)
        stmt = (
            select(KnowledgeVectorChunkModel, KnowledgeDocumentModel, distance.label("distance"))
            .join(KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id)
            .where(KnowledgeDocumentModel.category.in_(learned_categories))
            .order_by(distance)
            .limit(top_k * 2)
        )
        rows = (await self.session.execute(stmt)).all()

        collected: Dict[str, DocumentChunk] = {}
        norm_prompt = remove_accents((prompt_text or "").lower())

        for chunk_model, doc_model, dist in rows:
            meta = chunk_model.metadata_ or doc_model.metadata_ or {}
            doc_conn = meta.get("connection_id")
            if connection_id and doc_conn and str(doc_conn) != str(connection_id):
                continue

            c_id = str(chunk_model.id)
            sim = round(max(0.0, 1.0 - float(dist)), 4)
            # Impulsar score si menciona una tabla presente en el prompt
            for rel_t in (meta.get("related_tables") or []):
                rel_norm = remove_accents(str(rel_t).lower())
                if len(rel_norm) >= 3 and re.search(rf"\b{re.escape(rel_norm)}\b", norm_prompt):
                    sim = max(sim, 0.96)

            collected[c_id] = DocumentChunk(
                id=c_id,
                document_id=str(chunk_model.document_id),
                chunk_index=chunk_model.chunk_index,
                chunk_text=chunk_model.chunk_text,
                metadata={"category": doc_model.category, "title": doc_model.title, **meta},
                similarity_score=sim
            )

        sorted_rules = sorted(collected.values(), key=lambda x: x.similarity_score or 0.0, reverse=True)
        return sorted_rules[:top_k]

    async def search_dynamic_knowledge_rules(
        self,
        query_embedding: List[float],
        user_id: str,
        connection_id: Optional[str] = None,
        top_k: int = 3,
        similarity_threshold: float = 0.75
    ) -> List[Dict[str, Any]]:
        """
        Recupera reglas activas de aprendizaje implícito (scope global o scope user del usuario actual).
        Exige status='verified' para global o status in ('candidate', 'verified') para user.
        Filtra por umbral de similitud coseno con prefijo search_query.
        """
        distance = KnowledgeVectorChunkModel.embedding.cosine_distance(query_embedding)
        
        stmt = (
            select(KnowledgeVectorChunkModel, KnowledgeDocumentModel, distance.label("distance"))
            .join(KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id)
            .where(
                (
                    (KnowledgeVectorChunkModel.scope == "global") & (KnowledgeVectorChunkModel.status == "verified")
                ) | (
                    (KnowledgeVectorChunkModel.scope == "user") & 
                    (KnowledgeVectorChunkModel.user_id == user_id) & 
                    (KnowledgeVectorChunkModel.status.in_(["candidate", "verified"]))
                )
            )
        )
        if connection_id:
            try:
                conn_uuid = uuid.UUID(str(connection_id))
                stmt = stmt.where(KnowledgeVectorChunkModel.connection_id == conn_uuid)
            except Exception:
                pass

        stmt = stmt.order_by(distance).limit(top_k * 2)
        rows = (await self.session.execute(stmt)).all()

        results = []
        for chunk, doc, dist in rows:
            sim = round(max(0.0, 1.0 - float(dist)), 4)
            if sim >= similarity_threshold:
                results.append({
                    "id": str(chunk.id),
                    "title": doc.title,
                    "target_entity": chunk.target_entity,
                    "target_column": chunk.target_column,
                    "prescriptive_condition": chunk.prescriptive_condition,
                    "content": chunk.chunk_text,
                    "similarity": sim,
                    "scope": chunk.scope
                })

        # Ordenar y cortar top_k
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    async def list_learned_rules(
        self,
        connection_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lista todas las cápsulas de aprendizaje registradas por el usuario."""
        learned_categories = ["custom_relation", "business_rule", "kpi_formula", "sql_example"]
        stmt = (
            select(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.category.in_(learned_categories))
            .order_by(KnowledgeDocumentModel.created_at.desc())
            .limit(100)
        )
        docs = (await self.session.execute(stmt)).scalars().all()
        items: List[Dict[str, Any]] = []
        for d in docs:
            meta = d.metadata_ or {}
            doc_conn = meta.get("connection_id")
            if connection_id and doc_conn and str(doc_conn) != str(connection_id):
                continue
            items.append({
                "id": str(d.id),
                "title": d.title,
                "category": d.category,
                "department": d.department,
                "content": d.content,
                "metadata": meta,
                "created_at": d.created_at.isoformat() if d.created_at else None
            })
        return items

    async def delete_learned_rule(self, document_id: str) -> bool:
        """Elimina una cápsula de conocimiento por su UUID."""
        try:
            doc_uuid = uuid.UUID(str(document_id))
        except Exception:
            return False

        doc = await self.session.get(KnowledgeDocumentModel, doc_uuid)
        if not doc:
            return False

        await self.session.delete(doc)
        await self.session.commit()
        return True

    async def attach_custom_relation_to_schema_docs(
        self,
        source_table: str,
        target_table: str,
        join_hint: str,
        connection_id: Optional[str] = None
    ) -> int:
        """
        Vincula una relación enseñada por el usuario (`custom_relation`) directamente
        en los metadatos `related_tables` y `join_hints` de los esquemas `db_schema`
        en pgvector para que la expansión `1-Hop` funcione inmediatamente.
        """
        if not source_table or not target_table:
            return 0

        stmt = (
            select(KnowledgeVectorChunkModel, KnowledgeDocumentModel)
            .join(KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id)
            .where(KnowledgeDocumentModel.category == "db_schema")
        )
        if connection_id:
            stmt = stmt.where(
                KnowledgeDocumentModel.metadata_["connection_id"].astext == str(connection_id)
            )

        rows = (await self.session.execute(stmt)).all()
        updated = 0
        src_low = source_table.strip().lower()
        tgt_low = target_table.strip().lower()

        for chunk_model, doc_model in rows:
            meta = dict(chunk_model.metadata_ or doc_model.metadata_ or {})
            t_name = str(meta.get("table_name", "")).strip()
            if not t_name:
                continue
            t_low = t_name.lower()
            if t_low not in (src_low, tgt_low):
                continue

            other_table = target_table if t_low == src_low else source_table
            rel_list = list(meta.get("related_tables") or [])
            if other_table not in rel_list:
                rel_list.append(other_table)

            hints_list = list(meta.get("join_hints") or [])
            if join_hint and join_hint not in hints_list:
                hints_list.insert(0, join_hint)

            meta["related_tables"] = rel_list
            meta["join_hints"] = hints_list
            chunk_model.metadata_ = dict(meta)
            doc_model.metadata_ = dict(meta)
            updated += 1

        if updated > 0:
            await self.session.commit()
        return updated
