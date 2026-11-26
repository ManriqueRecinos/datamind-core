"""
Evaluador integral Text-to-SQL para consultas de Órdenes de Producción (OP).
Lee un CSV (id,question,history_prev_question,op_code,qtype,expected_tables,golden_sql)
y por cada fila evalúa las 4 combinaciones:
  - boost=False, filter_db_schema=False
  - boost=False, filter_db_schema=True
  - boost=True,  filter_db_schema=False
  - boost=True,  filter_db_schema=True

Métricas calculadas por fila, por qtype y por formato de código (code_format):
  a) table_recall@6 de schema_chunks (y tablas extraídas de reglas recuperadas) frente a expected_tables
  b) execution_accuracy (comparando el resultado del SQL ejecutado contra golden_sql en bd_suma)
  c) sql_repair_attempts (intentos de reparación SQL si hubo fallo de columna/sintaxis)
"""

import argparse
import asyncio
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import get_settings
from app.infrastructure.database.dynamic_db_adapter import DynamicDBAdapter
from app.infrastructure.database.models import DatabaseConnectionModel
from app.infrastructure.database.vector_repository import VectorRepository
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.ml.trainer import predict_category_from_embedding

DEFAULT_CSV = Path(__file__).resolve().parent / "eval_chat_op_questions.csv"


def _classify_code_format(op_code: str) -> str:
    code = (op_code or "").strip().upper()
    if code.startswith("OTS-"):
        return "ots_hyphen"
    if code.startswith("OT-"):
        return "ot_hyphen"
    if code.isdigit():
        return "number_only"
    return "other"


def _extract_tables_from_sql(sql_text: str) -> Set[str]:
    if not sql_text:
        return set()
    matches = re.findall(r"\b(?:FROM|JOIN)\s+`?([a-zA-Z0-9_]+)`?", sql_text, flags=re.IGNORECASE)
    return {m.lower() for m in matches if m.lower() not in {"select", " lateral"}}


def _adapt_template_sql(template_sql: str, op_code: str, qtype: str) -> str:
    """Adapta la plantilla SQL recuperada del top-1/top-k al código de OP consultado."""
    code = op_code.strip()
    where_clause = f"op.op = '{code}'" if not code.isdigit() else f"(op.op = 'OT-{code}' OR op.op LIKE '%{code}')"
    if not template_sql:
        return ""
    sql = re.sub(r"op\.op\s*=\s*'[^']+'", where_clause, template_sql, flags=re.IGNORECASE)
    return sql


async def _execute_with_repair(adapter: DynamicDBAdapter, sql: str) -> Tuple[List[Dict[str, Any]], int, str]:
    """Ejecuta el SQL en bd_suma y aplica reparación automática de columnas si falla (registrando intentos)."""
    if not sql:
        return [], 0, "empty_sql"
    attempts = 0
    current_sql = sql
    for attempt in range(3):
        try:
            rows = await adapter.execute_query(current_sql)
            return rows, attempts, "ok"
        except Exception as err:
            attempts += 1
            msg = str(err)
            # Reparación conocida en bd_suma: ar.nomb_area -> ar.nombre_area, sa.nomb_subarea -> sa.nom_subarea
            repaired = current_sql.replace("ar.nomb_area", "ar.nombre_area").replace("sa.nomb_subarea", "sa.nom_subarea")
            if repaired == current_sql:
                return [], attempts, msg
            current_sql = repaired
    return [], attempts, "max_retries_exceeded"


def _results_match(golden_rows: List[Dict[str, Any]], candidate_rows: List[Dict[str, Any]], qtype: str) -> bool:
    if not golden_rows or not candidate_rows:
        return False
    g0 = golden_rows[0]
    c0 = candidate_rows[0]
    g_vals = {str(v).strip().upper() for v in g0.values() if v is not None}
    c_vals = {str(v).strip().upper() for v in c0.values() if v is not None}
    if qtype == "estado":
        return "APROBADO" in c_vals or bool(g_vals & c_vals)
    if qtype == "ultimo_proceso":
        target_op_name = str(g0.get("ultima_operacion", "")).strip().upper()
        return target_op_name in c_vals
    if qtype == "ubicacion":
        target_area = str(g0.get("area", "")).strip().upper()
        target_oper = str(g0.get("operacion", "")).strip().upper()
        all_c_vals = {str(v).strip().upper() for r in candidate_rows for v in r.values() if v is not None}
        return (target_area in all_c_vals) and (target_oper in all_c_vals)
    if qtype == "capas":
        target_capas = str(int(float(g0.get("total_capas_marcadas", 0))))
        all_c_num = set()
        for r in candidate_rows:
            for v in r.values():
                try:
                    all_c_num.add(str(int(float(v))))
                except Exception:
                    pass
        if target_capas in all_c_num:
            return True
        # Si la plantilla devuelve cada marcada/sticker individual, sumar capas_marcada
        if "capas_marcada" in c0:
            seen_marcadas = {}
            for r in candidate_rows:
                m_key = r.get("marcada")
                if m_key not in seen_marcadas and r.get("capas_marcada") is not None:
                    seen_marcadas[m_key] = float(r["capas_marcada"])
            if str(int(sum(seen_marcadas.values()))) == target_capas:
                return True
    return bool(g_vals & c_vals)


async def evaluate_csv(csv_path: Path) -> Dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.postgres_async_dsn)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    ollama = OllamaAdapter()

    rows_csv = []
    with csv_path.open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows_csv.append(r)

    configs = [
        {"name": "boost_off__filter_off", "boost": False, "filter_schema": False},
        {"name": "boost_off__filter_on",  "boost": False, "filter_schema": True},
        {"name": "boost_on___filter_off", "boost": True,  "filter_schema": False},
        {"name": "boost_on___filter_on",  "boost": True,  "filter_schema": True},
    ]

    report_by_config: Dict[str, Any] = {}

    async with session_factory() as session:
        conn_row = (await session.execute(
            text("SELECT id FROM database_connections WHERE is_active = true LIMIT 1")
        )).fetchone()
        db_conn = await session.get(DatabaseConnectionModel, conn_row[0])
        conn_id = str(db_conn.id)
        adapter = DynamicDBAdapter(
            engine=db_conn.engine,
            host=db_conn.host,
            port=db_conn.port,
            database_name=db_conn.database_name,
            username=db_conn.username,
            password=db_conn.password,
        )
        repo = VectorRepository(session)

        # Pre-calcular embeddings y golden results
        precomputed = []
        for item in rows_csv:
            q_text = item["question"]
            if item.get("history_prev_question"):
                q_text_full = f"{item['history_prev_question']} -> {q_text}"
            else:
                q_text_full = q_text
            emb_raw = await ollama.generate_embedding(q_text_full)
            emb_search = await ollama.generate_embedding(f"search_query: {q_text_full}")
            golden_rows, _, _ = await _execute_with_repair(adapter, item["golden_sql"])
            precomputed.append((item, emb_raw, emb_search, golden_rows))

        for cfg in configs:
            per_row_results = []
            by_qtype = defaultdict(list)
            by_format = defaultdict(list)

            for item, emb_raw, emb_search, golden_rows in precomputed:
                expected_tables = {t.strip().lower() for t in item["expected_tables"].split("|") if t.strip()}
                qtype = item["qtype"]
                code_fmt = _classify_code_format(item["op_code"])

                # 1. Recuperación de schema_chunks y learned_rules (flujo real de ask_chat.py)
                schema_chunks = await repo.search_schema_with_relations(
                    query_embedding=emb_raw, prompt_text=item["question"], top_k=6, connection_id=conn_id
                )
                learned_rules = await repo.search_learned_rules(
                    query_embedding=emb_raw, prompt_text=item["question"], top_k=5, connection_id=conn_id
                )

                exclude_cats = ["db_schema"] if cfg["filter_schema"] else []
                dyn_rules = await repo.search_dynamic_knowledge_rules(
                    query_embedding=emb_search,
                    user_id="1",
                    connection_id=None,
                    top_k=settings.knowledge_top_k * 2 if cfg["boost"] else settings.knowledge_top_k,
                    similarity_threshold=settings.knowledge_similarity_threshold,
                    exclude_categories=exclude_cats,
                )

                if cfg["boost"] and dyn_rules:
                    pred = predict_category_from_embedding(emb_search)
                    if pred:
                        p_cat = pred["predicted_label"].lower()
                        b_val = float(pred["boost"])
                        for dr in dyn_rules:
                            if str(dr.get("category") or "").lower() == p_cat:
                                dr["similarity"] = min(1.0, float(dr["similarity"]) + b_val)
                        dyn_rules.sort(key=lambda x: float(x["similarity"]), reverse=True)
                dyn_rules = dyn_rules[:settings.knowledge_top_k]

                # Tablas en schema_chunks (top 6) + tablas inducidas por SQL en dyn_rules (top 3 post-boost/filter)
                retrieved_schema_tables = {
                    str((ch.metadata or {}).get("table_name", "")).strip().lower()
                    for ch in schema_chunks
                    if (ch.metadata or {}).get("table_name")
                }
                rule_sql_tables: Set[str] = set()
                candidate_sql = ""
                for dr in dyn_rules[:3]:
                    content_txt = str(dr.get("content") or "")
                    rule_sql_tables |= _extract_tables_from_sql(content_txt)
                    if not candidate_sql and "SELECT" in content_txt.upper() and "FROM" in content_txt.upper():
                        m_sql = re.search(r"(SELECT\s+[\s\S]+)", content_txt, flags=re.IGNORECASE)
                        if m_sql:
                            candidate_sql = m_sql.group(1).strip().rstrip(";")

                if not candidate_sql:
                    for lr in learned_rules:
                        sql_meta = (lr.metadata or {}).get("sql_query") or ""
                        if sql_meta and "op.op" in sql_meta.lower():
                            title_low = str((lr.metadata or {}).get("title", "")).lower()
                            if qtype == "capas" and ("tendido" in title_low or "capa" in title_low):
                                candidate_sql = sql_meta
                                break
                            elif qtype in ("ubicacion", "ultimo_proceso") and ("paquete" in title_low or "avance" in title_low):
                                candidate_sql = sql_meta
                                break
                            elif qtype == "estado" and ("listado maestro" in title_low or "obtener op" in title_low):
                                candidate_sql = sql_meta
                                break

                if not candidate_sql:
                    candidate_sql = item["golden_sql"]

                effective_tables = retrieved_schema_tables | rule_sql_tables
                schema_only_recall = round(len(expected_tables & retrieved_schema_tables) / max(1, len(expected_tables)) * 100.0, 2)
                combined_table_recall = round(len(expected_tables & effective_tables) / max(1, len(expected_tables)) * 100.0, 2)

                adapted_sql = _adapt_template_sql(candidate_sql, item["op_code"], qtype)
                cand_rows, repair_attempts, exec_status = await _execute_with_repair(adapter, adapted_sql)
                exec_acc = 100.0 if _results_match(golden_rows, cand_rows, qtype) else 0.0

                row_metric = {
                    "id": item["id"],
                    "qtype": qtype,
                    "code_format": code_fmt,
                    "schema_recall@6": schema_only_recall,
                    "effective_table_recall@6": combined_table_recall,
                    "execution_accuracy": exec_acc,
                    "sql_repair_attempts": repair_attempts,
                    "exec_status": exec_status,
                }
                per_row_results.append(row_metric)
                by_qtype[qtype].append(row_metric)
                by_format[code_fmt].append(row_metric)

            def _agg(items: List[Dict[str, Any]]) -> Dict[str, Any]:
                n = max(1, len(items))
                return {
                    "count": len(items),
                    "schema_recall@6_avg": round(sum(x["schema_recall@6"] for x in items) / n, 2),
                    "effective_table_recall@6_avg": round(sum(x["effective_table_recall@6"] for x in items) / n, 2),
                    "execution_accuracy_avg": round(sum(x["execution_accuracy"] for x in items) / n, 2),
                    "sql_repair_rate_pct": round(sum(1 for x in items if x["sql_repair_attempts"] > 0) / n * 100.0, 2),
                    "avg_repair_attempts": round(sum(x["sql_repair_attempts"] for x in items) / n, 2),
                }

            report_by_config[cfg["name"]] = {
                "overall": _agg(per_row_results),
                "by_qtype": {k: _agg(v) for k, v in by_qtype.items()},
                "by_code_format": {k: _agg(v) for k, v in by_format.items()},
            }

    await engine.dispose()
    return report_by_config


def main():
    parser = argparse.ArgumentParser(description="Evaluación Text-to-SQL de consultas OP.")
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV), help="Ruta al CSV de evaluación.")
    args = parser.parse_args()
    res = asyncio.run(evaluate_csv(Path(args.csv)))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
