"""
Script de evaluación comparativa de Retrieval (Hit@K y MRR) en 4 variantes:
1. base: sin filtro de categoría (incluye db_schema), sin boost
2. category_filter: excluyendo db_schema, sin boost
3. filter_plus_prefixes: excluyendo db_schema + re-embedding en copia con prefijo 'search_document: ' y consulta con 'search_query: '
4. filter_plus_boost: excluyendo db_schema + boost neuronal

Uso:
    python scripts/eval_retrieval.py [--csv ruta/preguntas.csv] [--k 5]
Formato CSV:
    question,expected_document_id
"""

import argparse
import asyncio
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.ml.dataset import _parse_pgvector
from app.infrastructure.ml.trainer import predict_category_from_embedding


def _cosine_sim_matrix(matrix: np.ndarray, vec: np.ndarray) -> np.ndarray:
    m_norm = matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-9)
    v_norm = vec / max(float(np.linalg.norm(vec)), 1e-9)
    return m_norm @ v_norm


def _evaluate_rankings(
    ranked_doc_ids_per_query: List[List[str]],
    expected_doc_ids: List[str],
    ks: Tuple[int, ...] = (1, 3, 5),
) -> Dict[str, Any]:
    hits = {k: 0 for k in ks}
    rr_sum = 0.0
    n = max(1, len(expected_doc_ids))

    for ranked, exp_id in zip(ranked_doc_ids_per_query, expected_doc_ids):
        # Deduplicar document_ids preservando orden de aparición
        seen = []
        for d in ranked:
            if d not in seen:
                seen.append(d)
        for k in ks:
            if exp_id in seen[:k]:
                hits[k] += 1
        if exp_id in seen:
            rank_pos = seen.index(exp_id) + 1
            rr_sum += 1.0 / rank_pos

    out = {f"hit@{k}": round(hits[k] / n * 100.0, 2) for k in ks}
    out["mrr"] = round(rr_sum / n, 4)
    out["queries"] = len(expected_doc_ids)
    return out


async def _load_chunks_from_db(engine) -> List[Dict[str, Any]]:
    q = text("""
        SELECT
            kc.id::text AS chunk_id,
            kd.id::text AS doc_id,
            kd.title AS title,
            kd.category AS category,
            kc.chunk_text AS chunk_text,
            kc.embedding::text AS embedding_text
        FROM knowledge_vector_chunks kc
        JOIN knowledge_documents kd ON kd.id = kc.document_id
        WHERE kc.embedding IS NOT NULL
          AND kc.scope = 'global'
          AND kc.status = 'verified'
    """)
    async with engine.connect() as conn:
        rows = (await conn.execute(q)).fetchall()
    chunks = []
    for r in rows:
        vec = _parse_pgvector(r[5])
        if len(vec) == 768:
            chunks.append({
                "chunk_id": r[0],
                "doc_id": r[1],
                "title": r[2],
                "category": r[3],
                "chunk_text": r[4],
                "embedding": vec,
            })
    return chunks


async def _build_or_load_questions(csv_path: Path | None, chunks: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    if csv_path and csv_path.exists():
        pairs = []
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                q = (row.get("question") or "").strip()
                d = (row.get("expected_document_id") or "").strip()
                if q and d:
                    pairs.append((q, d))
        if pairs:
            return pairs

    # Si no se provee CSV, construye 30 pares de prueba derivados de los documentos no-esquema
    by_doc: Dict[str, Dict[str, Any]] = {}
    for ch in chunks:
        if ch["category"] != "db_schema" and ch["doc_id"] not in by_doc:
            by_doc[ch["doc_id"]] = ch

    pairs: List[Tuple[str, str]] = []
    for doc_id, ch in by_doc.items():
        title = (ch["title"] or "").strip()
        snippet = " ".join((ch["chunk_text"] or "").strip().split()[:14])
        if title:
            pairs.append((f"¿Cómo aplica la regla o consulta sobre {title}?", doc_id))
        if snippet:
            pairs.append((f"Necesito información de: {snippet}", doc_id))
        if len(pairs) >= 40:
            break
    return pairs


async def run_evaluation(csv_path: Path | None = None) -> Dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.postgres_async_dsn)
    ollama = OllamaAdapter()

    try:
        chunks = await _load_chunks_from_db(engine)
        qa_pairs = await _build_or_load_questions(csv_path, chunks)

        all_matrix = np.array([c["embedding"] for c in chunks], dtype=np.float32)
        non_schema_indices = [i for i, c in enumerate(chunks) if c["category"] != "db_schema"]
        non_schema_chunks = [chunks[i] for i in non_schema_indices]
        non_schema_matrix = all_matrix[non_schema_indices]

        # Re-embeber en memoria (copia no destructiva) los chunks no-esquema con prefijo 'search_document: '
        prefixed_doc_vecs = []
        for c in non_schema_chunks:
            emb = await ollama.generate_embedding(f"search_document: {c['chunk_text']}")
            prefixed_doc_vecs.append(emb)
        prefixed_non_schema_matrix = np.array(prefixed_doc_vecs, dtype=np.float32)

        rankings_base: List[List[str]] = []
        rankings_filter: List[List[str]] = []
        rankings_prefixed: List[List[str]] = []
        rankings_boost: List[List[str]] = []
        expected_docs: List[str] = []

        for question, exp_doc_id in qa_pairs:
            expected_docs.append(exp_doc_id)
            q_vec_prefixed = np.array(await ollama.generate_embedding(f"search_query: {question}"), dtype=np.float32)

            # 1. Base (todos los chunks, incluido db_schema)
            sims_all = _cosine_sim_matrix(all_matrix, q_vec_prefixed)
            idx_all = np.argsort(-sims_all)[:10]
            rankings_base.append([chunks[i]["doc_id"] for i in idx_all])

            # 2. Filtro de categoría (excluye db_schema)
            sims_filt = _cosine_sim_matrix(non_schema_matrix, q_vec_prefixed)
            idx_filt = np.argsort(-sims_filt)[:10]
            rankings_filter.append([non_schema_chunks[i]["doc_id"] for i in idx_filt])

            # 3. Filtro + prefijos consistentes (search_document: vs search_query:)
            sims_pref = _cosine_sim_matrix(prefixed_non_schema_matrix, q_vec_prefixed)
            idx_pref = np.argsort(-sims_pref)[:10]
            rankings_prefixed.append([non_schema_chunks[i]["doc_id"] for i in idx_pref])

            # 4. Filtro + Boost neuronal
            pred = predict_category_from_embedding(q_vec_prefixed.tolist())
            sims_boost = sims_filt.copy()
            if pred:
                pred_cat = pred["predicted_label"].lower()
                boost_val = float(pred["boost"])
                for i, c in enumerate(non_schema_chunks):
                    if str(c["category"]).lower() == pred_cat:
                        sims_boost[i] = min(1.0, float(sims_boost[i]) + boost_val)
            idx_boost = np.argsort(-sims_boost)[:10]
            rankings_boost.append([non_schema_chunks[i]["doc_id"] for i in idx_boost])

        return {
            "total_evaluated_questions": len(qa_pairs),
            "non_schema_chunks_reembedded_in_memory": len(non_schema_chunks),
            "variants": {
                "1_base_unfiltered": _evaluate_rankings(rankings_base, expected_docs),
                "2_category_filter_no_db_schema": _evaluate_rankings(rankings_filter, expected_docs),
                "3_category_filter_plus_search_document_prefix": _evaluate_rankings(rankings_prefixed, expected_docs),
                "4_category_filter_plus_neural_boost": _evaluate_rankings(rankings_boost, expected_docs),
            },
        }
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Evaluación de variantes de Retrieval RAG.")
    parser.add_argument("--csv", type=str, default=None, help="Ruta opcional a CSV (question,expected_document_id)")
    args = parser.parse_args()
    csv_path = Path(args.csv) if args.csv else None
    report = asyncio.run(run_evaluation(csv_path))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
