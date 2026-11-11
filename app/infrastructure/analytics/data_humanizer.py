"""Módulo de Humanización de Datos y Enmascaramiento de Seguridad."""

import re
from typing import Any, Dict, List, Set, Tuple

# Patrón estricto de columnas sensibles que NUNCA deben mostrarse ni exponerse
SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(?i)(password|passwd|pass|token|secret|hash|salt|remember_token|auth_key|private_key)"
)

# Diccionario maestro de traducción de identificadores técnicos a lenguaje corporativo
BUSINESS_COLUMN_DICTIONARY: Dict[str, str] = {
    # Identificadores y personas
    "id": "ID",
    "user_id": "ID de Usuario",
    "name": "Nombre",
    "user_name": "Nombre de Usuario",
    "username": "Usuario",
    "user_username": "Usuario",
    "email": "Correo Electrónico",
    "user_email": "Correo Electrónico",
    "phone": "Teléfono",
    "status": "Estado",
    "role": "Rol",
    "role_name": "Rol",
    "roles_name": "Rol",
    "permission": "Permiso",
    "permission_name": "Permiso",
    "permissions_name": "Permiso",
    "interface": "Pantalla / Interfaz",
    "interface_name": "Pantalla / Interfaz",
    "interfaces_name": "Pantalla / Interfaz",
    "ecosystem": "Ecosistema",
    "ecosystem_name": "Ecosistema",
    "ecosystems_name": "Ecosistema",
    "guard_name": "Guardia de Autenticación",
    "created_at": "Fecha de Creación",
    "user_created_at": "Fecha de Creación",
    "updated_at": "Última Actualización",
    "user_updated_at": "Última Actualización",
    "password_changed_at": "Último Cambio de Contraseña",
    "user_password_changed_at": "Último Cambio de Contraseña",

    # Organizaciones y empresas
    "company_id": "ID de Empresa",
    "current_company_id": "ID de Empresa Actual",
    "user_current_company_id": "ID de Empresa Actual",
    "company_name": "Empresa Asignada",
    "companies_name": "Empresa",
    "acronym": "Sigla / Código",
    "address": "Dirección",
    "description": "Descripción",
    "company_description": "Descripción de la Empresa",
    "companies_description": "Descripción de la Empresa",

    # Inventario y repuestos
    "codigo": "Código",
    "item_code": "Código de Artículo",
    "parte_maquina": "Parte / Repuesto",
    "id_parte_maquina": "ID de Parte",
    "stock": "Existencias / Stock",
    "cantidad": "Cantidad",
    "costo": "Costo",
    "precio": "Precio",
    "categoria": "Categoría",
    "ubicacion": "Ubicación en Bodega",
    "maquina": "Máquina Asociada",
    "tipo_parte": "Tipo de Repuesto"
}

# Diccionario de lemas y plurales comunes en español para entidades de base de datos
ENTITY_LEMMA_MAP: Dict[str, str] = {
    # Usuarios
    "usuario": "users",
    "usuarios": "users",
    "users": "users",
    "user": "users",
    "perfil": "users",
    "perfiles": "users",
    "empleado": "users",
    "empleados": "users",
    "colaborador": "users",
    "colaboradores": "users",

    # Empresas / Compañías
    "empresa": "companies",
    "empresas": "companies",
    "companies": "companies",
    "company": "companies",
    "compania": "companies",
    "companias": "companies",
    "sucursal": "companies",
    "sucursales": "companies",

    # Repuestos y partes
    "repuesto": "inventario_partes",
    "repuestos": "inventario_partes",
    "parte": "parte_maquina",
    "partes": "parte_maquina",
    "aditamento": "parte_maquina",
    "aditamentos": "parte_maquina",
    "aguja": "parte_maquina",
    "agujas": "parte_maquina",

    # Clientes
    "cliente": "customers",
    "clientes": "customers",
    "customer": "customers",
    "customers": "customers",

    # Roles, Permisos y Catálogos de Seguridad RBAC
    "rol": "roles",
    "roles": "roles",
    "role": "roles",
    "permiso": "permissions",
    "permisos": "permissions",
    "permission": "permissions",
    "permissions": "permissions",
    "ecosistema": "ecosystems",
    "ecosistemas": "ecosystems",
    "ecosystem": "ecosystems",
    "ecosystems": "ecosystems",
    "interfaz": "interfaces",
    "interfaces": "interfaces",
    "interface": "interfaces"
}


class DataHumanizer:
    """Provee purga de columnas sensibles y conversión a lenguaje de negocios legible."""

    @staticmethod
    def is_sensitive(column_name: str) -> bool:
        """Verifica si una columna contiene credenciales o información confidencial."""
        if not column_name:
            return False
        return bool(SENSITIVE_COLUMN_PATTERN.search(column_name.strip()))

    @staticmethod
    def humanize_label(col_name: str) -> str:
        """Traduce un nombre técnico a una etiqueta humana en español."""
        if not col_name:
            return ""
        clean_key = col_name.strip().lower()

        # 1. Búsqueda directa en diccionario de negocios
        if clean_key in BUSINESS_COLUMN_DICTIONARY:
            return BUSINESS_COLUMN_DICTIONARY[clean_key]

        # 2. Remover prefijos técnicos usuales: user_, tbl_, company_, id_
        cleaned = re.sub(r"^(tbl_|tb_|cat_|mae_|dim_|user_|company_)", "", clean_key)

        if cleaned in BUSINESS_COLUMN_DICTIONARY:
            return BUSINESS_COLUMN_DICTIONARY[cleaned]

        # 3. Fallback heurístico: reemplazar guiones bajos por espacios y capitalizar
        words = cleaned.replace("_", " ").split()
        return " ".join([w.capitalize() if w.lower() not in ("de", "del", "la", "el", "en", "y") else w for w in words])

    @classmethod
    def sanitize_and_humanize(
        cls,
        columns: List[str],
        rows: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, str]]:
        """
        1. Pone en lista negra y elimina columnas sensibles (passwords, tokens).
        2. Mapea cada columna restante a su etiqueta legible en español de negocios.
        Retorna: (human_columns, sanitized_rows, column_mapping)
        """
        # Filtrar columnas sensibles
        safe_original_cols = [c for c in columns if not cls.is_sensitive(c)]
        
        # Crear mapeo técnico -> humano
        mapping: Dict[str, str] = {}
        human_cols: List[str] = []
        for col in safe_original_cols:
            human_label = cls.humanize_label(col)
            # Evitar colisiones de nombres humanos duplicados
            if human_label in human_cols:
                human_label = f"{human_label} ({col})"
            mapping[col] = human_label
            human_cols.append(human_label)

        # Transformar filas
        sanitized_rows: List[Dict[str, Any]] = []
        for row in rows:
            new_row: Dict[str, Any] = {}
            for col in safe_original_cols:
                h_col = mapping[col]
                val = row.get(col)
                # Formatear booleanos a Sí / No
                if isinstance(val, bool):
                    val = "Sí" if val else "No"
                new_row[h_col] = val
            sanitized_rows.append(new_row)

        return human_cols, sanitized_rows, mapping

    @staticmethod
    def resolve_unambiguous_entity(prompt_text: str, synced_table_names: List[str]) -> Tuple[bool, str]:
        """
        Evalúa si la pregunta del usuario menciona inequívocamente la entidad raíz principal
        en español (ej. 'usuarios' -> 'users').
        Retorna: (is_unambiguous, target_table_name)
        """
        if not prompt_text or not synced_table_names:
            return False, ""

        clean_prompt = prompt_text.lower()
        synced_lower_set = {t.lower() for t in synced_table_names}

        # Extraer tokens del prompt
        tokens = re.findall(r"\b[a-zA-ZáéíóúñÁÉÍÓÚÑ_]+\b", clean_prompt)

        matched_targets: Set[str] = set()

        for token in tokens:
            t_clean = token.lower()
            # 1. Comprobar si el token es un lema mapeado
            if t_clean in ENTITY_LEMMA_MAP:
                mapped_table = ENTITY_LEMMA_MAP[t_clean]
                if mapped_table in synced_lower_set:
                    matched_targets.add(mapped_table)

            # 2. Comprobar si el token coincide directamente con una tabla sincronizada
            if t_clean in synced_lower_set:
                matched_targets.add(t_clean)

        # Si coincide exactamente con una sola tabla raíz principal, no hay ambigüedad
        if len(matched_targets) == 1:
            return True, list(matched_targets)[0]

        return False, ""
