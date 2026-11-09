"""Pruebas unitarias para el particionador de texto (Fase 3)."""

import pytest
from app.infrastructure.parsers.text_chunker import TextChunker


def test_chunker_empty_text():
    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    assert chunker.split_text("") == []
    assert chunker.split_text("   ") == []


def test_chunker_short_text():
    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    text = "Este es un texto corto que cabe completo."
    chunks = chunker.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunker_long_text_overlap():
    chunker = TextChunker(chunk_size=50, chunk_overlap=15)
    text = "El proceso de manufactura textil requiere inspección visual cada hora para evitar defectos en la tela."
    chunks = chunker.split_text(text)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 60  # margen razonable por límites de palabra


def test_chunker_invalid_overlap():
    with pytest.raises(ValueError):
        TextChunker(chunk_size=50, chunk_overlap=60)
