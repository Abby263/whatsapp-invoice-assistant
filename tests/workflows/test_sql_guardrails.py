"""Tests for SQL execution guardrails."""

import pytest

from utils import sql_guardrails
from workflows.invoice_query_workflow import convert_to_sql, execute_query


def test_prepare_sql_for_execution_requires_bound_user_scope():
    prepared = sql_guardrails.prepare_sql_for_execution(
        "SELECT * FROM invoices WHERE user_id = :user_id",
        user_id="7",
    )

    assert prepared == "SELECT * FROM invoices WHERE user_id = :user_id LIMIT 500"


def test_prepare_sql_for_execution_accepts_scoped_invoice_alias():
    prepared = sql_guardrails.prepare_sql_for_execution(
        "SELECT inv.id FROM invoices inv WHERE inv.user_id = :user_id",
        user_id=7,
    )

    assert prepared.endswith("LIMIT 500")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM invoices",
        "WITH x AS (SELECT :user_id AS user_id) SELECT * FROM invoices, x WHERE x.user_id = :user_id",
        "SELECT * FROM invoices WHERE user_id = 1",
        "SELECT * FROM invoices WHERE user_id = '7'",
        "SELECT * FROM invoices; DROP TABLE invoices",
        "SELECT * FROM invoices -- WHERE user_id = :user_id",
        "DELETE FROM invoices WHERE user_id = :user_id",
    ],
)
def test_prepare_sql_for_execution_rejects_unsafe_queries(sql):
    with pytest.raises(sql_guardrails.SQLGuardrailError):
        sql_guardrails.prepare_sql_for_execution(sql, user_id=7)


def test_prepare_sql_for_execution_caps_large_limits():
    prepared = sql_guardrails.prepare_sql_for_execution(
        "SELECT * FROM invoices WHERE user_id = :user_id LIMIT 5000",
        user_id=7,
        max_rows=500,
    )

    assert prepared.endswith("LIMIT 500")


@pytest.mark.asyncio
async def test_execute_query_rejects_unscoped_sql_before_database_call():
    class FakeSession:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("unsafe SQL must not reach the database")

    result = await execute_query(
        "SELECT * FROM invoices",
        session=FakeSession(),
        user_id="7",
    )

    assert result["success"] is False
    assert "user_id = :user_id" in result["error"]


@pytest.mark.asyncio
async def test_execute_query_binds_user_id_and_enforces_limit():
    captured = {}

    class FakeResult:
        def keys(self):
            return ["id", "vendor"]

        def fetchall(self):
            return [(1, "Acme")]

    class FakeSession:
        def execute(self, statement, params):
            captured["statement"] = str(statement)
            captured["params"] = params
            return FakeResult()

    result = await execute_query(
        "SELECT id, vendor FROM invoices WHERE user_id = :user_id",
        session=FakeSession(),
        user_id="7",
    )

    assert result["success"] is True
    assert result["results"] == [{"id": 1, "vendor": "Acme"}]
    assert captured["params"]["user_id"] == 7
    assert captured["statement"].endswith("LIMIT 500")


@pytest.mark.asyncio
async def test_convert_to_sql_rejects_non_database_user_id():
    result = await convert_to_sql("Show my receipts", user_id="not-a-db-id")

    assert "error" in result
    assert "signed-in user context" in result["error"]
