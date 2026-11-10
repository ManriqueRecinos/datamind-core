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


def test_detect_chart_request():
    wants, chart_type = IntentClassifier.detect_chart_request("Hazme un gráfico de barras de las ventas por estado")
    assert wants is True
    assert chart_type == "bar"

    wants_pie, chart_type_pie = IntentClassifier.detect_chart_request("Muestra una grafica de pastel por departamento")
    assert wants_pie is True
    assert chart_type_pie == "pie"

    wants_line, chart_type_line = IntentClassifier.detect_chart_request("Graficar la tendencia mensual de ordenes")
    assert wants_line is True
    assert chart_type_line == "line"

    wants_none, _ = IntentClassifier.detect_chart_request("¿Qué tablas están registradas?")
    assert wants_none is False


def test_analyze_columns_option_a_guided_vs_explicit():
    from app.use_cases.ask_chat import AskChatUseCase

    columns = ["estado_rollo", "codigo_orden", "departamento", "peso_kg", "metros"]
    rows = [
        {"estado_rollo": "ACTIVO", "codigo_orden": "ORD-01", "departamento": "TEJIDO", "peso_kg": 125.5, "metros": 340},
        {"estado_rollo": "RETENIDO", "codigo_orden": "ORD-02", "departamento": "TINTORERIA", "peso_kg": 88.0, "metros": 210},
    ]

    # Caso 1 (Opción A): Solicitud general entre tablas sin especificar qué columnas exactas graficar -> needs_field_selection = True
    cfg_guided = AskChatUseCase.analyze_columns_for_chart(
        columns=columns,
        rows=rows,
        wants_chart=True,
        preferred_type="bar",
        prompt="Revísame los rollos vinculados con las órdenes y hazme un gráfico"
    )
    assert cfg_guided["wants_chart"] is True
    assert cfg_guided["needs_field_selection"] is True
    assert "estado_rollo" in cfg_guided["dimension_columns"]
    assert "peso_kg" in cfg_guided["metric_columns"]
    assert "column_samples" in cfg_guided

    # Caso 2: Solicitud donde el usuario ya indicó explícitamente el Eje X y el Eje Y -> needs_field_selection = False
    cfg_explicit = AskChatUseCase.analyze_columns_for_chart(
        columns=columns,
        rows=rows,
        wants_chart=True,
        preferred_type="bar",
        prompt="Genera el gráfico de barras agrupando por departamento y sumando peso_kg"
    )
    assert cfg_explicit["wants_chart"] is True
    assert cfg_explicit["needs_field_selection"] is False
    assert cfg_explicit["x_field"] == "departamento"
    assert cfg_explicit["y_field"] == "peso_kg"
    assert cfg_explicit["aggregation"] == "SUM"


def test_relational_fk_inference_and_embedding_enrichment():
    from app.infrastructure.database.dynamic_db_adapter import DynamicDBAdapter
    from app.use_cases.manage_connections import ManageConnectionsUseCase
    from app.use_cases.ask_chat import AskChatUseCase

    # Simular introspección de dos tablas relacionadas: `usuario` (con id_empresa) y `empresa` (con id y nombre_empresa)
    raw_columns = [
        {"table_name": "usuario", "column_name": "id", "data_type": "int", "is_nullable": "NO", "column_comment": ""},
        {"table_name": "usuario", "column_name": "nombre_usuario", "data_type": "varchar", "is_nullable": "NO", "column_comment": ""},
        {"table_name": "usuario", "column_name": "id_empresa", "data_type": "int", "is_nullable": "NO", "column_comment": ""},
        {"table_name": "usuario", "column_name": "salario", "data_type": "decimal", "is_nullable": "YES", "column_comment": ""},
        {"table_name": "empresa", "column_name": "id", "data_type": "int", "is_nullable": "NO", "column_comment": ""},
        {"table_name": "empresa", "column_name": "nombre_empresa", "data_type": "varchar", "is_nullable": "NO", "column_comment": ""},
        {"table_name": "empresa", "column_name": "razon_social", "data_type": "varchar", "is_nullable": "YES", "column_comment": ""},
    ]

    grouped = DynamicDBAdapter._group_columns_by_table(raw_columns, fk_rows=[])
    by_name = {t["table_name"]: t for t in grouped}

    usuario_meta = by_name["usuario"]
    empresa_meta = by_name["empresa"]

    # Verificar que usuario.id_empresa fue detectado apuntando a empresa.id y extrajo sus columnas descriptivas
    assert "empresa" in usuario_meta["related_tables"]
    assert len(usuario_meta["foreign_keys"]) == 1
    fk = usuario_meta["foreign_keys"][0]
    assert fk["column"] == "id_empresa"
    assert fk["referenced_table"] == "empresa"
    assert fk["referenced_column"] == "id"
    assert "nombre_empresa" in fk["descriptive_columns"]

    # Verificar relación inversa en `empresa`
    assert "usuario" in empresa_meta["related_tables"]
    assert len(empresa_meta["referenced_by"]) == 1

    # Verificar que el texto de embedding generado incluye la instrucción de JOIN con el nombre descriptivo
    embed_text, join_hints = ManageConnectionsUseCase.build_relational_schema_embedding_text(
        conn_name="ERP Corporativo",
        engine_label="MariaDB/MySQL",
        database_name="erp_db",
        table=usuario_meta
    )
    assert "JOIN empresa ON usuario.id_empresa = empresa.id" in embed_text
    assert "empresa.nombre_empresa" in embed_text
    assert any("JOIN empresa ON usuario.id_empresa = empresa.id" in h for h in join_hints)

    # Verificar que analyze_columns_for_chart excluye `id_empresa` de dimension_columns y sugiere `nombre_empresa`
    joined_cols = ["id_empresa", "nombre_empresa", "nombre_usuario", "salario"]
    joined_rows = [
        {"id_empresa": 10, "nombre_empresa": "Industrias Alfa", "nombre_usuario": "Carlos", "salario": 1200},
        {"id_empresa": 20, "nombre_empresa": "Textiles Beta", "nombre_usuario": "Ana", "salario": 1450},
    ]
    chart_cfg = AskChatUseCase.analyze_columns_for_chart(
        columns=joined_cols,
        rows=joined_rows,
        wants_chart=True,
        preferred_type="bar",
        prompt="Hazme un gráfico de usuarios por empresa"
    )
    assert "id_empresa" in chart_cfg["foreign_key_columns"]
    assert "id_empresa" not in chart_cfg["dimension_columns"]
    assert "nombre_empresa" in chart_cfg["dimension_columns"]
    assert chart_cfg["x_field"] == "nombre_empresa"


def test_teach_knowledge_intent_and_conditional_chart_suppression():
    """
    Verifica el caso exacto reportado por el usuario:
    Cuando el usuario le enseña una relación entre tablas en el chat mencionando
    'Cuando el usuario pida datos o gráficos por empresa...', la IA debe clasificarlo como
    `teach_knowledge` y NO disparar gráficos ni tablas.
    """
    user_teaching_prompt = (
        "La tabla users se relaciona con la tabla companies uniendo users.current_company_id= companies.id. "
        "Cuando el usuario pida datos o gráficos por empresa, nunca muestres current_company_id; "
        "haz siempre JOIN empresa y muestra empresa.name."
    )

    assert IntentClassifier.is_teaching_statement(user_teaching_prompt) is True
    assert IntentClassifier.classify(user_teaching_prompt) == "teach_knowledge"

    wants_chart, _ = IntentClassifier.detect_chart_request(user_teaching_prompt)
    assert wants_chart is False

    fmt = IntentClassifier.detect_output_format(user_teaching_prompt)
    assert fmt["wants_chart"] is False
    assert fmt["wants_table"] is False
    assert fmt["output_mode"] == "text_only"

    capsule = IntentClassifier.extract_teaching_capsule(user_teaching_prompt)
    assert capsule["category"] == "custom_relation"
    assert capsule["source_table"] == "users"
    assert capsule["source_column"] == "current_company_id"
    assert capsule["target_table"] == "companies"
    assert capsule["target_column"] == "id"
    assert capsule["label_column"] == "name"


def test_detect_output_format_table_vs_chart_vs_text():
    # 1. Solo pregunta en texto -> ni gráfico ni tabla abiertos por defecto
    fmt_text = IntentClassifier.detect_output_format("¿Cuántos usuarios activos hay por empresa?")
    assert fmt_text["wants_chart"] is False
    assert fmt_text["wants_table"] is False
    assert fmt_text["output_mode"] == "text_only"

    # 2. Pide explícitamente una tabla
    fmt_table = IntentClassifier.detect_output_format("Hazme una tabla con los usuarios y su empresa")
    assert fmt_table["wants_table"] is True
    assert fmt_table["wants_chart"] is False
    assert fmt_table["output_mode"] == "table"

    # 3. Pide explícitamente un gráfico
    fmt_chart = IntentClassifier.detect_output_format("Hazme un gráfico de barras de usuarios por empresa")
    assert fmt_chart["wants_chart"] is True
    assert fmt_chart["wants_table"] is False
    assert fmt_chart["output_mode"] == "chart"




