"""Generador de libros Excel (.xlsx) estilizados con openpyxl para reportes corporativos."""

from datetime import datetime, timezone
import io
from typing import Any, Dict, List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from app.domain.entities import QueryDataset


class ExcelGenerator:
    """Construye libros de cálculo profesionales con la paleta de diseño de DataMind AI."""

    # Paleta DataMind (#0476D9, #0468BF, #4B89BF, #99D0F2, #F2F2F2)
    HEADER_FILL = PatternFill(start_color="0468BF", end_color="0468BF", fill_type="solid")  # Azul profundo
    ZEBRA_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")   # Gris neutro claro
    HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="0468BF")
    SUBTITLE_FONT = Font(name="Calibri", size=9, italic=True, color="4B89BF")
    DATA_FONT = Font(name="Calibri", size=10)
    BORDER_THIN = Side(border_style="thin", color="99D0F2")
    CELL_BORDER = Border(left=BORDER_THIN, right=BORDER_THIN, top=BORDER_THIN, bottom=BORDER_THIN)

    def generate_excel_bytes(self, dataset: QueryDataset, title: Optional[str] = None) -> bytes:
        """Genera y retorna los bytes binarios de un archivo .xlsx estilizado."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Reporte de Datos"
        ws.views.sheetView[0].showGridLines = True

        # 1. Título y Membrete superior
        report_title = title or "Reporte de Consulta - DataMind AI"
        ws["A1"] = report_title
        ws["A1"].font = self.TITLE_FONT

        generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        ws["A2"] = f"Generado el: {generated_at} | Total registros: {dataset.row_count}"
        ws["A2"].font = self.SUBTITLE_FONT

        # Fila en blanco
        start_row = 4

        # 2. Cabeceras de columnas
        columns = dataset.columns
        for col_idx, col_name in enumerate(columns, start=1):
            cell = ws.cell(row=start_row, column=col_idx)
            cell.value = col_name.replace("_", " ").upper()
            cell.fill = self.HEADER_FILL
            cell.font = self.HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = self.CELL_BORDER

        ws.row_dimensions[start_row].height = 26

        # 3. Filas de datos
        current_row = start_row + 1
        for row_data in dataset.rows:
            for col_idx, col_name in enumerate(columns, start=1):
                cell = ws.cell(row=current_row, column=col_idx)
                val = row_data.get(col_name)

                # Formatear números si aplica
                if isinstance(val, float):
                    cell.value = val
                    cell.number_format = "#,##0.00"
                elif isinstance(val, int):
                    cell.value = val
                    cell.number_format = "#,##0"
                else:
                    cell.value = str(val) if val is not None else ""

                cell.font = self.DATA_FONT
                cell.border = self.CELL_BORDER
                cell.alignment = Alignment(vertical="center")
                if (current_row - start_row) % 2 == 0:
                    cell.fill = self.ZEBRA_FILL
            current_row += 1

        # 4. Habilitar autofiltro en cabeceras
        if columns:
            last_col_letter = get_column_letter(len(columns))
            ws.auto_filter.ref = f"A{start_row}:{last_col_letter}{current_row - 1}"

        # 5. Ajuste automático de ancho de columnas
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row >= start_row and cell.value:
                    val_str = str(cell.value)
                    max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        # 6. Escribir a buffer en memoria
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()
