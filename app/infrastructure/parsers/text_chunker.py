"""Particionador de texto recursivo con solapamiento para ingesta RAG."""

from typing import List


class TextChunker:
    """Divide textos extensos en fragmentos más pequeños conservando contexto mediante overlap."""

    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 80):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap debe ser estrictamente menor que chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        """Divide el texto limpiando espacios redundantes y aplicando solapamiento."""
        cleaned_text = " ".join(text.split())
        if not cleaned_text:
            return []

        if len(cleaned_text) <= self.chunk_size:
            return [cleaned_text]

        chunks: List[str] = []
        start = 0
        text_length = len(cleaned_text)

        while start < text_length:
            end = start + self.chunk_size

            # Si no es el final del texto, buscar el último espacio para no cortar palabras
            if end < text_length:
                last_space = cleaned_text.rfind(" ", start, end)
                if last_space != -1 and last_space > start:
                    end = last_space

            chunk = cleaned_text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Avanzar aplicando el solapamiento
            start = end - self.chunk_overlap
            if start < 0 or start >= end:
                start = end

        return chunks
