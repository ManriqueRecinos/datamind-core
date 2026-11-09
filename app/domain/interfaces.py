"""Contratos e interfaces abstractas del dominio para inversión de dependencias."""

from typing import Any, AsyncIterator, Dict, List, Optional, Protocol
from app.domain.entities import DocumentChunk, QueryDataset


class VectorStoreInterface(Protocol):
    """Contrato para almacenamiento y búsqueda semántica en la base de datos vectorial."""

    async def save_chunks(self, chunks: List[DocumentChunk]) -> int:
        """Guarda fragmentos vectorizados."""
        ...

    async def search_similar(
        self, query_embedding: List[float], top_k: int = 4, filter_category: Optional[str] = None
    ) -> List[DocumentChunk]:
        """Recupera fragmentos similares por distancia coseno."""
        ...


class RelationalDbInterface(Protocol):
    """Contrato para ejecución de consultas de solo lectura en la base externa (MariaDB)."""

    async def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Ejecuta una consulta SQL SELECT validada."""
        ...

    async def introspect_schema(self) -> List[Dict[str, Any]]:
        """Extrae el catálogo de tablas y columnas del esquema de la base de datos."""
        ...


class LLMClientInterface(Protocol):
    """Contrato para interactuar con el motor de IA local (Ollama)."""

    async def generate_embedding(self, text: str) -> List[float]:
        """Genera un vector embedding de 768 dimensiones para el texto dado."""
        ...

    async def generate_completion(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Genera una respuesta de texto completa."""
        ...

    async def stream_completion(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Transmite la respuesta token por token en tiempo real."""
        ...


class ExcelExporterInterface(Protocol):
    """Contrato para generar hojas de cálculo binarias en formato .xlsx."""

    def generate_excel_bytes(self, dataset: QueryDataset, title: Optional[str] = None) -> bytes:
        """Construye el libro .xlsx estilizado y retorna sus bytes binarios."""
        ...
