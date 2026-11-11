"""Script de calibración empírica de umbral de similitud para nomic-embed-text."""

import asyncio
import json
import math
from typing import List, Dict, Any
from app.infrastructure.llm.ollama_adapter import OllamaAdapter


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


async def calibrate():
    with open("tests/fixtures/embedding_calibration_pairs.json", "r", encoding="utf-8") as f:
        pairs = json.load(f)

    ollama = OllamaAdapter()
    
    print(f"Calibrando con {len(pairs)} pares de consulta-regla independientes...")
    
    # Pre-vectorizar documentos únicos con prefijo search_document:
    doc_embeddings: Dict[str, List[float]] = {}
    for p in pairs:
        doc_text = p["document"]
        if doc_text not in doc_embeddings:
            doc_embeddings[doc_text] = await ollama.generate_embedding(f"search_document: {doc_text}")

    # Vectorizar consultas con prefijo search_query: y calcular similitudes
    scores = []
    for p in pairs:
        query_text = p["query"]
        q_emb = await ollama.generate_embedding(f"search_query: {query_text}")
        d_emb = doc_embeddings[p["document"]]
        sim = cosine_similarity(q_emb, d_emb)
        scores.append({
            "id": p["id"],
            "query": query_text,
            "document": p["document"],
            "is_relevant": p["is_relevant"],
            "similarity": round(sim, 4)
        })

    print("\n--- RESUMEN DE SCORES POR GRUPO ---")
    pos_scores = [s["similarity"] for s in scores if s["is_relevant"]]
    neg_scores = [s["similarity"] for s in scores if not s["is_relevant"]]

    print(f"Positivos ({len(pos_scores)}): Min={min(pos_scores):.4f}, Max={max(pos_scores):.4f}, Promedio={sum(pos_scores)/len(pos_scores):.4f}")
    print(f"Negativos ({len(neg_scores)}): Min={min(neg_scores):.4f}, Max={max(neg_scores):.4f}, Promedio={sum(neg_scores)/len(neg_scores):.4f}")

    # Evaluar umbrales de 0.65 a 0.85 con paso 0.01
    best_f1 = -1.0
    best_threshold = 0.75
    metrics = []

    print("\n| Umbral | Precision | Recall | F1-Score | FP (Falsos Pos) | FN (Falsos Neg) |")
    print("|---|---|---|---|---|---|")

    for t_int in range(65, 86, 2):
        t = t_int / 100.0
        tp = sum(1 for s in scores if s["is_relevant"] and s["similarity"] >= t)
        fp = sum(1 for s in scores if not s["is_relevant"] and s["similarity"] >= t)
        fn = sum(1 for s in scores if s["is_relevant"] and s["similarity"] < t)
        tn = sum(1 for s in scores if not s["is_relevant"] and s["similarity"] < t)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics.append({
            "threshold": t,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "fp": fp,
            "fn": fn
        })

        if f1 > best_f1:
            best_f1 = f1
            best_threshold = t

        print(f"| {t:.2f} | {precision:.4f} | {recall:.4f} | {f1:.4f} | {fp} | {fn} |")

    print(f"\n>>> Umbral Óptimo Seleccionado: {best_threshold:.2f} (F1-Score: {best_f1:.4f})")
    
    with open("tests/fixtures/calibration_results.json", "w", encoding="utf-8") as out_f:
        json.dump({
            "best_threshold": best_threshold,
            "best_f1": best_f1,
            "pos_avg": sum(pos_scores)/len(pos_scores),
            "neg_avg": sum(neg_scores)/len(neg_scores),
            "metrics": metrics,
            "scores": scores
        }, out_f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(calibrate())
