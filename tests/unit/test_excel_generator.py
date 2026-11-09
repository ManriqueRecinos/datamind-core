"""Pruebas unitarias para el generador de reportes Excel (Fase 6)."""

import io
import openpyxl
import pytest
from app.domain.entities import QueryDataset
from app.infrastructure.export.excel_generator import ExcelGenerator


def test_excel_generator_structure_and_styles():
    generator = ExcelGenerator()
    dataset = QueryDataset(
        dataset_id="ds_unit_test_1",
        sql_executed="SELECT id, proceso, horas_retraso FROM ordenes",
        columns=["id", "proceso", "horas_retraso"],
        rows=[
            {"id": 1, "proceso": "Corte", "horas_retraso": 4.5},
            {"id": 2, "proceso": "Ensamble", "horas_retraso": 1.2}
        ],
        row_count=2
    )

    excel_bytes = generator.generate_excel_bytes(dataset, title="Reporte Test DataMind")
    assert excel_bytes is not None
    assert len(excel_bytes) > 0

    # Abrir el libro con openpyxl para verificar celdas y formato
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb.active

    # Título en A1
    assert ws["A1"].value == "Reporte Test DataMind"

    # Cabeceras en fila 4
    assert ws["A4"].value == "ID"
    assert ws["B4"].value == "PROCESO"
    assert ws["C4"].value == "HORAS RETRASO"

    # Datos en filas 5 y 6
    assert ws["A5"].value == 1
    assert ws["B5"].value == "Corte"
    assert ws["C5"].value == 4.5
    assert ws["C5"].number_format == "#,##0.00"

    assert ws["A6"].value == 2
    assert ws["B6"].value == "Ensamble"
    assert ws["C6"].value == 1.2
