"""Extracción de embeddings (768-dim), document_id y etiquetas reales desde PostgreSQL (pgvector)."""

import hashlib
import json
from typing import Any, Dict, List, Tuple
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


def _parse_pgvector(raw_vec) -> List[float]:
    if isinstance(raw_vec, (list, tuple)):
        return [float(x) for x in raw_vec]
    if isinstance(raw_vec, str):
        cleaned = raw_vec.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            return [float(x) for x in json.loads(cleaned)]
    return []


async def load_pgvector_training_dataset() -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, List[Dict[str, Any]]]:
    """
    Carga embeddings reales (768-dim), etiquetas y document_id desde pgvector.
    Deduplica por hash de texto y similitud coseno > 0.98 antes del split.
    """
    settings = get_settings()
    engine = create_async_engine(settings.postgres_async_dsn)

    query = text("""
        SELECT
            kc.embedding::text AS embedding_text,
            COALESCE(NULLIF(kd.category, ''), 'general') AS label,
            kd.id::text AS doc_id,
            COALESCE(kc.chunk_text, '') AS chunk_text
        FROM knowledge_vector_chunks kc
        INNER JOIN knowledge_documents kd ON kd.id = kc.document_id
        WHERE kc.embedding IS NOT NULL
        ORDER BY kd.id, kc.chunk_index
    """)

    vectors: List[List[float]] = []
    raw_labels: List[str] = []
    raw_doc_ids: List[str] = []
    seen_text_hashes: Dict[str, str] = {}
    label_conflicts: List[Dict[str, Any]] = []

    try:
        async with engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            for row in rows:
                vec = _parse_pgvector(row[0])
                if len(vec) != 768:
                    continue
                lbl = str(row[1]).strip()
                doc_id = str(row[2]).strip()
                norm_text = " ".join(str(row[3]).strip().lower().split())
                text_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()

                if text_hash in seen_text_hashes:
                    if seen_text_hashes[text_hash] != lbl:
                        label_conflicts.append({
                            "type": "exact_text",
                            "label_a": seen_text_hashes[text_hash],
                            "label_b": lbl,
                            "doc_id": doc_id,
                        })
                    continue

                seen_text_hashes[text_hash] = lbl
                vectors.append(vec)
                raw_labels.append(lbl)
                raw_doc_ids.append(doc_id)
    finally:
        await engine.dispose()

    if not vectors:
        raise ValueError("No se encontraron embeddings de 768 dimensiones en pgvector para entrenar.")

    X_arr = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(X_arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X_norm = X_arr / norms

    keep_indices: List[int] = []
    for i in range(len(X_arr)):
        is_dup = False
        if keep_indices:
            sims = X_norm[keep_indices] @ X_norm[i]
            max_pos = int(np.argmax(sims))
            if float(sims[max_pos]) > 0.98:
                kept_idx = keep_indices[max_pos]
                if raw_labels[kept_idx] != raw_labels[i]:
                    label_conflicts.append({
                        "type": "cosine_gt_0.98",
                        "label_a": raw_labels[kept_idx],
                        "label_b": raw_labels[i],
                        "similarity": round(float(sims[max_pos]), 4),
                    })
                is_dup = True
        if not is_dup:
            keep_indices.append(i)

    X_dedup = X_arr[keep_indices]
    labels_dedup = [raw_labels[i] for i in keep_indices]
    docs_dedup = np.array([raw_doc_ids[i] for i in keep_indices])

    unique_labels = sorted(set(labels_dedup))
    label_to_idx = {lbl: idx for idx, lbl in enumerate(unique_labels)}
    y = np.array([label_to_idx[lbl] for lbl in labels_dedup], dtype=np.int32)

    return X_dedup, y, unique_labels, docs_dedup, label_conflicts
