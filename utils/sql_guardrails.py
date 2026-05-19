"""SQL execution guardrails for user-scoped analytics queries."""

from __future__ import annotations

import re
from typing import Any, Optional


class SQLGuardrailError(ValueError):
    """Raised when generated SQL is unsafe to execute."""


_DANGEROUS_COMMANDS = {
    "ALTER",
    "CREATE",
    "DELETE",
    "DROP",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "INSERT",
    "MERGE",
    "REVOKE",
    "TRUNCATE",
    "UPDATE",
}


def coerce_user_id(user_id: Any) -> Optional[int]:
    """Return the integer application user id, or raise for spoof-prone values."""

    if user_id is None:
        return None
    if isinstance(user_id, bool):
        raise SQLGuardrailError("A valid signed-in user context is required.")
    if isinstance(user_id, int):
        return user_id

    text = str(user_id).strip()
    if text.isdigit():
        return int(text)
    raise SQLGuardrailError("A valid signed-in user context is required.")


def sanitize_sql(query: str) -> str:
    """Allow only one read-only SELECT/WITH statement with comments removed."""

    if not query or not query.strip():
        raise SQLGuardrailError("Empty SQL query")

    sanitized = _strip_sql_comments(query).strip().rstrip(";").strip()
    if not sanitized:
        raise SQLGuardrailError("Empty SQL query")
    if ";" in sanitized:
        raise SQLGuardrailError("Multiple SQL statements are not allowed")
    if not re.match(r"^\s*(SELECT|WITH)\b", sanitized, re.IGNORECASE):
        raise SQLGuardrailError("Only SELECT queries are allowed")

    for command in _DANGEROUS_COMMANDS:
        if re.search(rf"\b{command}\b", sanitized, re.IGNORECASE):
            raise SQLGuardrailError(f"SQL command is not allowed: {command}")

    return sanitized


def require_user_scope(sql: str, user_id: Any) -> str:
    """Require SQL to be scoped by a bound :user_id parameter."""

    if coerce_user_id(user_id) is None:
        raise SQLGuardrailError("A signed-in user context is required to execute analytics queries.")

    normalized = _strip_sql_comments(sql)
    if _has_literal_user_filter(normalized):
        raise SQLGuardrailError("SQL must use the bound :user_id parameter, not a literal user id.")
    if not has_user_scope(normalized):
        raise SQLGuardrailError("SQL must include a user_id = :user_id scope.")
    return sql


def has_user_scope(sql: str) -> bool:
    """Return whether SQL contains an explicit bound user scope."""

    normalized = " ".join(sql.split())
    user_scoped_tables = ("invoices", "media", "generated_invoices")

    for table in user_scoped_tables:
        if re.search(rf"\b{table}\.user_id\s*=\s*:user_id\b", normalized, flags=re.IGNORECASE):
            return True
        if re.search(
            rf"\bFROM\s+(?:public\.)?{table}\s+WHERE\b.*\buser_id\s*=\s*:user_id\b",
            normalized,
            flags=re.IGNORECASE,
        ):
            return True

        aliases = _aliases_for_table(normalized, table)
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\.user_id\s*=\s*:user_id\b", normalized, flags=re.IGNORECASE):
                return True

    invoice_subquery_patterns = [
        r"\b(?:\w+\.)?invoice_id\s+IN\s*\(\s*SELECT\s+(?:id|invoices\.id)\s+FROM\s+invoices\s+WHERE\s+user_id\s*=\s*:user_id\s*\)",
        r"\b(?:\w+\.)?invoice_id\s+IN\s*\(\s*SELECT\s+(?:\w+\.)?id\s+FROM\s+invoices\s+(?:AS\s+)?(\w+)\s+WHERE\s+\1\.user_id\s*=\s*:user_id\s*\)",
    ]
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in invoice_subquery_patterns)


def enforce_limit(sql: str, max_rows: int = 500) -> str:
    """Ensure generated SQL has a bounded LIMIT."""

    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", sql, flags=re.IGNORECASE)
    if limit_match:
        try:
            current_limit = int(limit_match.group(1))
        except ValueError:
            current_limit = max_rows
        if current_limit > max_rows:
            return (
                sql[:limit_match.start(1)]
                + str(max_rows)
                + sql[limit_match.end(1):]
            )
        return sql

    offset_match = re.search(r"\bOFFSET\b", sql, flags=re.IGNORECASE)
    if offset_match:
        return f"{sql[:offset_match.start()].rstrip()} LIMIT {max_rows} {sql[offset_match.start():].lstrip()}"
    return f"{sql} LIMIT {max_rows}"


def prepare_sql_for_execution(sql: str, user_id: Any, max_rows: int = 500) -> str:
    """Run all SQL guardrails used immediately before execution."""

    sanitized = sanitize_sql(sql)
    scoped = require_user_scope(sanitized, user_id)
    return enforce_limit(scoped, max_rows=max_rows)


def _strip_sql_comments(sql: str) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n\r]*", " ", without_block_comments)


def _aliases_for_table(sql: str, table: str) -> set[str]:
    aliases = set()
    sql_keywords = {
        "WHERE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "FULL",
        "INNER",
        "OUTER",
        "CROSS",
        "ON",
        "GROUP",
        "ORDER",
        "LIMIT",
    }
    for match in re.finditer(
        rf"\b(?:FROM|JOIN)\s+(?:public\.)?{table}\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        sql,
        flags=re.IGNORECASE,
    ):
        alias = match.group(1)
        if alias.upper() not in sql_keywords:
            aliases.add(alias)
    return aliases


def _has_literal_user_filter(sql: str) -> bool:
    literal_patterns = [
        r"\b(?:\w+\.)?user_id\s*=\s*\d+\b",
        r"\b(?:\w+\.)?user_id\s*=\s*'[^']+'",
        r'\b(?:\w+\.)?user_id\s*=\s*"[^"]+"',
    ]
    return any(re.search(pattern, sql, flags=re.IGNORECASE) for pattern in literal_patterns)
