"""
Script de benchmarking de memoria RAM y latencia para operaciones sobre adjuntos.
Simula la carga, inferencia de esquema y ejecución de consultas analíticas en DuckDB y Polars.
"""

import os
import sys

# Asegurar que la raíz del proyecto esté en el sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import tracemalloc
import psutil
import polars as pl
import duckdb

from app.infrastructure.analytics.attachment_analytics_engine import AttachmentAnalyticsEngine
from app.infrastructure.security.file_security_validator import FileSecurityValidator


def run_benchmark():
    process = psutil.Process(os.getpid())
    tracemalloc.start()
    
    ram_initial_mb = process.memory_info().rss / (1024 * 1024)
    print(f"[*] RAM inicial proceso: {ram_initial_mb:.2f} MB")
    
    # 1. Generar archivo CSV sintético de 50,000 filas
    print("[*] Generando dataset sintético de 50,000 registros...")
    t0 = time.perf_counter()
    data = {
        "id": list(range(1, 50001)),
        "codigo_repuesto": [f"REP-{i:05d}" for i in range(1, 50001)],
        "categoria": ["Mecanico", "Electrico", "Neumatico", "Hidraulico", "Electronico"] * 10000,
        "stock": [i % 500 for i in range(1, 50001)],
        "costo_unitario": [round((i % 100) * 1.5 + 0.5, 2) for i in range(1, 50001)]
    }
    df = pl.DataFrame(data)
    csv_path = "storage/temp_bench_50k.csv"
    os.makedirs("storage", exist_ok=True)
    df.write_csv(csv_path)
    t_gen = time.perf_counter() - t0
    print(f"[*] Archivo CSV generado en {t_gen:.3f} s ({os.path.getsize(csv_path) / (1024*1024):.2f} MB)")

    # 2. Inferencia y procesamiento con AttachmentAnalyticsEngine
    t1 = time.perf_counter()
    row_count, schema_info = AttachmentAnalyticsEngine.process_and_inspect_file(csv_path, "text/csv")
    t_inspect = time.perf_counter() - t1
    print(f"[*] Inferencia de esquema completada en {t_inspect:.3f} s. Filas estimadas: {row_count}")

    # 3. Consulta analítica en conexión DuckDB sandboxed
    conn = AttachmentAnalyticsEngine.get_sandboxed_duckdb_conn(allow_file_read=True)
    t2 = time.perf_counter()
    conn.execute(f"CREATE VIEW repuestos_bench AS SELECT * FROM read_csv_auto('{csv_path.replace(os.sep, '/')}')")
    res = conn.execute("""
        SELECT 
            categoria,
            COUNT(*) as total_items,
            SUM(stock) as stock_total,
            ROUND(AVG(costo_unitario), 2) as costo_promedio,
            ROUND(SUM(stock * costo_unitario), 2) as valor_inventario
        FROM repuestos_bench
        GROUP BY categoria
        ORDER BY valor_inventario DESC
    """).fetchall()
    t_query = time.perf_counter() - t2
    print(f"[*] Agregación compleja DuckDB completada en {t_query:.3f} s:")
    for row in res:
        print(f"    - Categoria {row[0]}: {row[1]} repuestos, valor inventario: ${row[4]:,.2f}")
    conn.close()

    # Medir memoria pico y final
    current_tracemalloc, peak_tracemalloc = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ram_peak_mb = process.memory_info().rss / (1024 * 1024)
    
    print("\n" + "="*50)
    print("RESULTADOS DEL BENCHMARK")
    print("="*50)
    print(f"RAM Pico Proceso:           {ram_peak_mb:.2f} MB")
    print(f"RAM Pico Tracemalloc:       {peak_tracemalloc / (1024 * 1024):.2f} MB")
    print(f"Delta RAM consumida:        {ram_peak_mb - ram_initial_mb:.2f} MB")
    print(f"Límite máximo permitido:    256.00 MB")
    print(f"Estado de cumplimiento:     {'CUMPLE (SEGURO)' if (ram_peak_mb - ram_initial_mb) < 256 else 'EXCEDE'}")
    print("="*50)

    # Limpieza
    if os.path.exists(csv_path):
        os.remove(csv_path)


if __name__ == "__main__":
    run_benchmark()
