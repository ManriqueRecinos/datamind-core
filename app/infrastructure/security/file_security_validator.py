"""Servicio perimetral de validación de seguridad de archivos (MIME real, Zip-Bombs, límites y fórmulas)."""

import os
import zipfile
from typing import Tuple, Optional, Any
from fastapi import HTTPException, status


class FileSecurityValidator:
    """
    Valida la seguridad de archivos antes de su procesamiento:
    1. Límite perimetral de tamaño (máx 15 MB).
    2. Inspección de tipo MIME real por Magic Bytes (cabecera hexadecimal).
    3. Protección contra Zip-Bombs para archivos comprimidos (XLSX/XLS).
    """

    MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
    MAX_UNCOMPRESSED_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
    MAX_ZIP_COMPRESSION_RATIO = 100.0  # Ratio 100:1

    # Firmas mágicas de cabecera (Magic Bytes)
    MAGIC_ZIP = b"PK\x03\x04"  # Cabecera estándar ZIP (XLSX, DOCX, etc.)
    MAGIC_PDF = b"%PDF-"       # Cabecera estándar PDF
    ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".pdf", ".docx"}

    @classmethod
    def validate_file_size(cls, file_size: int):
        """Valida que el archivo no supere el tamaño máximo perimetral."""
        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo excede el tamaño máximo permitido de {cls.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            )

    @classmethod
    def detect_real_mime(cls, header_bytes: bytes, filename: str) -> str:
        """
        Detecta el tipo MIME real leyendo los primeros bytes del archivo y la extensión.
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Extensión no permitida '{ext}'. Formatos soportados: CSV, TSV, XLSX, XLS, PDF, DOCX."
            )

        if ext == ".pdf":
            if not header_bytes.startswith(cls.MAGIC_PDF):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo no coincide con una firma válida de PDF (cabecera corrupta o falsificada)."
                )
            return "application/pdf"

        if ext == ".docx":
            if not header_bytes.startswith(cls.MAGIC_ZIP):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo no coincide con una firma válida de DOCX (cabecera corrupta o falsificada)."
                )
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        if ext in {".xlsx", ".xls"}:
            if not header_bytes.startswith(cls.MAGIC_ZIP) and not header_bytes.startswith(b"\xd0\xcf\x11\xe0"): # OLE2 XLS
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo no coincide con una firma válida de Excel (cabecera corrupta o formato falsificado)."
                )
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == ".xlsx" else "application/vnd.ms-excel"

        if ext == ".csv":
            return "text/csv"
        if ext == ".tsv":
            return "text/tab-separated-values"

        return "application/octet-stream"

    @classmethod
    def check_zip_bomb(cls, file_input: Any):
        """
        Inspecciona archivos ZIP (como XLSX) para prevenir ataques de denegación de servicio por descompresión explosiva.
        """
        if isinstance(file_input, (str, os.PathLike)):
            if not zipfile.is_zipfile(file_input):
                return
            zf_context = zipfile.ZipFile(file_input, "r")
        else:
            # Archivo en memoria o BytesIO
            zf_context = zipfile.ZipFile(file_input, "r")

        total_uncompressed = 0
        total_compressed = 0

        with zf_context as zf:
            for info in zf.infolist():
                total_uncompressed += info.file_size
                total_compressed += info.compress_size

                if total_uncompressed > cls.MAX_UNCOMPRESSED_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Archivo rechazado por seguridad: el contenido descomprimido excede el límite de 50 MB (posible Zip-Bomb)."
                    )

            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                if ratio > cls.MAX_ZIP_COMPRESSION_RATIO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Archivo rechazado por seguridad: ratio de compresión excesivo ({ratio:.1f}:1)."
                    )

    @classmethod
    def sanitize_cell_value(cls, val: str) -> str:
        """
        Previene la inyección de fórmulas de hoja de cálculo forzando las celdas que inicien con =, +, -, @ a texto plano.
        """
        if isinstance(val, str) and val.startswith(("=", "+", "-", "@")):
            return f"'{val}"
        return val
