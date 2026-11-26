from app.infrastructure.analytics.data_humanizer import DataHumanizer

def test_humanize_entity_known_tables():
    assert DataHumanizer.humanize_entity("tallas_op_bajas") == "Registro de Bajas / Mermas de Talla"
    assert DataHumanizer.humanize_entity("tallas_op_bajas_operacion") == "Bajas de Talla por Operación"
    assert DataHumanizer.humanize_entity("celda") == "Celdas de Producción"
    assert DataHumanizer.humanize_entity("op") == "Órdenes de Producción"
    assert DataHumanizer.humanize_entity("estado_op_paquete") == "Movimientos y Paquetes de Producción"

def test_humanize_entity_fallback():
    assert DataHumanizer.humanize_entity("inventario_articulos_nuevos") == "Inventario Articulos Nuevos"

def test_resolve_unambiguous_entity_packages():
    synced = ["op", "celda", "tallas_op_bajas", "tallas_op_bajas_operacion"]
    is_unambiguous, target = DataHumanizer.resolve_unambiguous_entity("cuales son los codigos de esos paquetes?", synced)
    assert is_unambiguous is True
    assert target == "op"

def test_resolve_unambiguous_entity_celda():
    synced = ["op", "celda", "tallas_op_bajas"]
    is_unambiguous, target = DataHumanizer.resolve_unambiguous_entity("en que celda esta?", synced)
    assert is_unambiguous is True
    assert target == "celda"
