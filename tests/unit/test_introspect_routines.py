"""Pruebas unitarias para introspección y vectorización de funciones y procedimientos."""

from app.infrastructure.database.dynamic_db_adapter import DynamicDBAdapter
from app.use_cases.manage_connections import ManageConnectionsUseCase


def test_build_routine_embedding_text_includes_metadata():
    routine = {
        "schema_name": "public",
        "routine_name": "calcular_iva",
        "routine_type": "FUNCTION",
        "parameters": "monto numeric",
        "return_type": "numeric",
        "comment": "Calcula el IVA del 12%",
        "definition": "RETURN monto * 0.12;",
    }
    text = ManageConnectionsUseCase.build_routine_embedding_text(
        conn_name="ERP",
        engine_label="PostgreSQL",
        database_name="erp_db",
        routine=routine,
    )
    assert "FUNCTION" in text
    assert "calcular_iva" in text
    assert "monto numeric" in text
    assert "RETURN monto * 0.12;" in text


def test_group_columns_infers_identical_id_relationship():
    rows = [
        {"table_name": "rollo", "column_name": "id_rollo", "data_type": "int", "is_nullable": "NO", "column_comment": ""},
        {"table_name": "rollo", "column_name": "codigo", "data_type": "varchar", "is_nullable": "YES", "column_comment": ""},
        {"table_name": "documentos_rollo", "column_name": "id_documento", "data_type": "int", "is_nullable": "NO", "column_comment": ""},
        {"table_name": "documentos_rollo", "column_name": "id_rollo", "data_type": "int", "is_nullable": "NO", "column_comment": ""},
    ]
    tables = {t["table_name"]: t for t in DynamicDBAdapter._group_columns_by_table(rows, fk_rows=[])}
    fks = tables["documentos_rollo"]["foreign_keys"]
    assert any(
        fk["column"] == "id_rollo"
        and fk["referenced_table"] == "rollo"
        and fk["referenced_column"] == "id_rollo"
        and fk["relationship_type"] == "inferred_fk"
        for fk in fks
    )
