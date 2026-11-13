"""Pruebas unitarias para QueryBlueprint: parse, compile, roundtrip, guardrail y límites."""

import pytest
from app.domain.query_blueprint import (
    BaseTableSpec,
    JoinSpec,
    JoinType,
    OnCondition,
    OrderByItem,
    QueryBlueprint,
    SelectItem,
    SingleSelectBlueprint,
    UnionMode,
    UnionSpec,
    WhereCondition,
)
from app.use_cases.query_blueprint import QueryBlueprintUseCase


@pytest.fixture
def use_case():
    return QueryBlueprintUseCase()


def test_roundtrip_basic_select(use_case):
    sql = "SELECT id, name FROM users WHERE active = '1' ORDER BY id DESC LIMIT 20"
    bp = use_case.parse(sql, dialect="postgres")

    assert bp.primary.base.table == "users"
    assert len(bp.primary.select) == 2
    assert len(bp.primary.where) == 1
    assert bp.primary.where[0].left == "active"
    assert len(bp.primary.order_by) == 1
    assert bp.primary.limit == 20

    compiled = use_case.compile(bp, dialect="postgres")
    assert "FROM users" in compiled
    assert "WHERE" in compiled
    assert "ORDER BY" in compiled
    assert "LIMIT 20" in compiled


def test_parse_and_compile_joins(use_case):
    sql = """
    SELECT u.id, u.name, r.role_name
    FROM users AS u
    LEFT JOIN role_user AS ru ON u.id = ru.user_id
    INNER JOIN roles AS r ON ru.role_id = r.id
    WHERE u.status = 'active'
    """
    bp = use_case.parse(sql, dialect="postgres")

    assert bp.primary.base.table == "users"
    assert bp.primary.base.alias == "u"
    assert len(bp.primary.joins) == 2

    # Primer join: LEFT
    j1 = bp.primary.joins[0]
    assert j1.type == JoinType.LEFT
    assert j1.table == "role_user"
    assert j1.alias == "ru"
    assert len(j1.on) == 1
    assert j1.on[0].left == "u.id"
    assert j1.on[0].right == "ru.user_id"

    # Segundo join: INNER
    j2 = bp.primary.joins[1]
    assert j2.type == JoinType.INNER
    assert j2.table == "roles"
    assert j2.alias == "r"

    compiled = use_case.compile(bp, dialect="postgres")
    assert "LEFT JOIN role_user AS ru" in compiled
    assert "INNER JOIN roles AS r" in compiled


def test_parse_and_compile_unions(use_case):
    sql = """
    SELECT id, email FROM customers
    UNION ALL
    SELECT id, email FROM employees
    """
    bp = use_case.parse(sql, dialect="postgres")

    assert bp.primary.base.table == "customers"
    assert len(bp.unions) == 1
    assert bp.unions[0].mode == UnionMode.UNION_ALL
    assert bp.unions[0].select_query.base.table == "employees"

    compiled = use_case.compile(bp, dialect="postgres")
    assert "UNION ALL" in compiled
    assert "FROM customers" in compiled
    assert "FROM employees" in compiled


def test_parse_cte_into_raw_blocks(use_case):
    sql = """
    WITH active_users AS (
        SELECT id, name FROM users WHERE active = 1
    )
    SELECT id, name FROM active_users
    """
    bp = use_case.parse(sql, dialect="postgres")

    assert len(bp.raw_blocks) == 1
    assert bp.raw_blocks[0].type == "cte"
    assert "WITH active_users AS" in bp.raw_blocks[0].content
    assert bp.primary.base.table == "active_users"

    compiled = use_case.compile(bp, dialect="postgres")
    assert "WITH active_users AS" in compiled
    assert "FROM active_users" in compiled


def test_reject_destructive_sql(use_case):
    destructive_sqls = [
        "DELETE FROM users WHERE id = 1",
        "DROP TABLE users",
        "TRUNCATE TABLE users",
        "UPDATE users SET name = 'hacked'",
        "INSERT INTO users (id) VALUES (1)",
    ]
    for sql in destructive_sqls:
        with pytest.raises(ValueError, match="Operación no permitida"):
            use_case.parse(sql, dialect="postgres")


def test_blueprint_validation_limits():
    # Probar que falle si supera 10 uniones
    primary = SingleSelectBlueprint(
        base=BaseTableSpec(table="tbl0"),
        select=[SelectItem(expr="*")]
    )
    excessive_unions = [
        UnionSpec(
            mode=UnionMode.UNION_ALL,
            select_query=SingleSelectBlueprint(
                base=BaseTableSpec(table=f"tbl{i}"),
                select=[SelectItem(expr="*")]
            )
        )
        for i in range(1, 12)
    ]

    with pytest.raises(ValueError, match="No se permiten más de 10 operaciones UNION"):
        QueryBlueprint(
            primary=primary,
            unions=excessive_unions
        )
