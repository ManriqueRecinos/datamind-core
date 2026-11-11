# Contratos de API y CLI: Conocimiento como Código (YAML)

**Especificación**: `specs/005-schema-knowledge-code-retrieval`  

---

## 1. Contrato del Comando CLI: `load_knowledge`

### Invocación:
```bash
python -m app.cli.load_knowledge --connection <SLUG_O_ID> [--check] [--explain]
```

### Argumentos:
| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `--connection` | `string` | Sí | Nombre (slug) o UUID de la conexión registrada en `database_connections`. |
| `--check` | `flag` | No | Modo dry-run: valida archivos YAML, sintaxis SQL y coincidencia de catálogo sin persistir en BD ni generar embeddings. |
| `--explain` | `flag` | No | Ejecuta `EXPLAIN` en la base de datos remota para cada consulta de `examples.yaml`. |

### Códigos de Salida (Exit Codes):
- `0`: Validación y carga completada exitosamente (o check exitoso).
- `1`: Error de validación de esquema (tabla o columna inexistente en `synced_tables`).
- `2`: Error de sintaxis SQL en `examples.yaml` (violación de `sqlglot` o sentencias distintas a `SELECT`).
- `3`: Conexión de base de datos no encontrada.

### Salida Estándar (Ejemplo):
```text
[*] Validando conexión: SUMAIE - MANRIQUE DEMO (8629a50c-7351-4cda-bc97-967be6637c7e)...
[*] Leyendo directorio: knowledge/demo_manrique/
    [OK] relations.yaml: 12 uniones verificadas contra synced_tables.
    [OK] examples.yaml: 8 consultas SQL validadas con sqlglot (SELECT puro).
    [OK] glossary.yaml: 15 términos y 4 columnas categóricas verificadas.
[*] Procesando cambios (Upsert por SHA256)...
    - Nuevos chunks: 5
    - Chunks sin cambios (idempotentes): 23
    - Chunks eliminados/obsoletos: 0
[+] Carga finalizada con éxito. 5 embeddings generados. Auditoría registrada.
```

---

## 2. Contrato de Archivos YAML de Conocimiento

### A. `relations.yaml`
```yaml
relations:
  - source_table: "inventario_repuestos.inventario_partes"
    source_column: "id_parte_maquina"
    target_table: "hop.parte_maquina"
    target_column: "id_parte_maquina"
    label_column: "nombre"
    description: "Une el registro de inventario físico con su definición técnica en el catálogo HOP"
```

### B. `examples.yaml`
```yaml
examples:
  - question: "¿Cuáles son las partes mecánicas con existencia crítica en bodega?"
    sql: |
      SELECT ip.numero_item, pm.nombre, st.existencia_actual, st.punto_reorden
      FROM inventario_repuestos.inventario_partes ip
      JOIN hop.parte_maquina pm ON ip.id_parte_maquina = pm.id_parte_maquina
      JOIN inventario_repuestos.inventario_partes_stock st ON st.id_inventario_partes = ip.id_inventario_partes
      WHERE st.existencia_actual <= st.punto_reorden AND ip.activo = TRUE
      LIMIT 100;
    explanation: "Filtra existencias por debajo del punto de reorden uniendo inventario y catálogo"
```

### C. `glossary.yaml`
```yaml
terms:
  - term: "looper"
    synonyms: ["garfio", "enlazador", "áncora"]
    target_table: "hop.parte_maquina"
    target_column: "nombre"
    note: "Pieza mecánica de formación de puntada en overlock y recubridora"

categorical_columns:
  - table: "inventario_repuestos.inventario_partes"
    column: "es_usado"
    values:
      - value: "true"
        description: "Repuesto reacondicionado o de segundo uso"
      - value: "false"
        description: "Repuesto nuevo de paquete"
```
