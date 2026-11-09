"""Pruebas unitarias para el clasificador de intención (Fase 5)."""

from app.use_cases.intent_classifier import IntentClassifier


def test_classify_general_chat():
    assert IntentClassifier.classify("Hola, buenos dias") == "general_chat"
    assert IntentClassifier.classify("Hola") == "general_chat"
    assert IntentClassifier.classify("Saludos") == "general_chat"
    assert IntentClassifier.classify("¿Quien eres?") == "general_chat"


def test_classify_data_query():
    assert IntentClassifier.classify("¿Cuantas ordenes estan pendientes?") == "data_query"
    assert IntentClassifier.classify("Listar las ordenes con retraso") == "data_query"
    assert IntentClassifier.classify("¿Cuales son los procesos con demora?") == "data_query"
    assert IntentClassifier.classify("Promedio de horas de retraso por tabla") == "data_query"


def test_classify_process_qa():
    assert IntentClassifier.classify("Explica la politica de calidad para telas defectuosas") == "process_qa"
    assert IntentClassifier.classify("Procedimiento para calibracion de maquinas") == "process_qa"
