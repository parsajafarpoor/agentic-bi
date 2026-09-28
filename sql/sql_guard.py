"""Deterministic SQL validation, run before anything touches the database.

Three layers, all fail-closed:
1. Keyword allowlist  - must start with SELECT/WITH, no DDL/DML keywords.
2. Structural parse    - sqlglot must parse it, and every table/column it
                         references must exist in the real schema.
3. Row cap             - a LIMIT is enforced so one bad aggregate-less
                         query can't return the whole table.

This is the only thing standing between an LLM's raw text output and
psycopg2.execute(). It must never rely on another LLM call to "check"
the SQL - that just repeats the same trust problem with extra latency.
"""

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from sql.schema_introspect import Schema

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|"
    r"COPY|CALL|MERGE|VACUUM|EXECUTE|DO)\b",
    re.IGNORECASE,
)

STARTS_WITH_SELECT = re.compile(r"^\s*(WITH|SELECT)\b", re.IGNORECASE)

DEFAULT_ROW_LIMIT = 500


@dataclass
class ValidationResult:
    ok: bool
    sql: str = ""
    reason: str = ""


def _extract_tables(parsed: exp.Expression) -> set[str]:
    return {table.name for table in parsed.find_all(exp.Table)}


def _extract_columns(parsed: exp.Expression) -> set[str]:
    return {
        column.name
        for column in parsed.find_all(exp.Column)
        if column.name != "*"
    }


def _extract_aliases(parsed: exp.Expression) -> set[str]:
    """Output aliases (e.g. SUM(...) AS revenue) are valid to reference
    in GROUP BY/ORDER BY/HAVING in Postgres, but sqlglot parses those
    references as plain Column nodes indistinguishable from real table
    columns. Collect alias names so they aren't flagged as unknown.
    """
    return {alias.alias for alias in parsed.find_all(exp.Alias) if alias.alias}


def validate_sql(sql: str, schema: Schema) -> ValidationResult:

    if not sql or not sql.strip():
        return ValidationResult(ok=False, reason="empty_sql")

    # Layer 1: keyword allowlist
    if not STARTS_WITH_SELECT.match(sql):
        return ValidationResult(ok=False, reason="does_not_start_with_select")

    if FORBIDDEN_KEYWORDS.search(sql):
        return ValidationResult(ok=False, reason="forbidden_keyword")

    if ";" in sql.strip().rstrip(";"):
        return ValidationResult(ok=False, reason="multiple_statements")

    # Layer 2: structural parse against the real schema
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception as exc:
        return ValidationResult(ok=False, reason=f"parse_error: {exc}")

    used_tables = _extract_tables(parsed)
    unknown_tables = used_tables - schema.tables
    if unknown_tables:
        return ValidationResult(ok=False, reason=f"unknown_tables: {unknown_tables}")

    used_columns = _extract_columns(parsed)
    known_aliases = _extract_aliases(parsed)
    unknown_columns = used_columns - schema.columns - known_aliases
    if unknown_columns:
        return ValidationResult(ok=False, reason=f"unknown_columns: {unknown_columns}")

    # Layer 3: enforce a row cap
    final_sql = sql.strip().rstrip(";")
    if not parsed.args.get("limit"):
        final_sql = f"{final_sql} LIMIT {DEFAULT_ROW_LIMIT}"

    return ValidationResult(ok=True, sql=final_sql)


if __name__ == "__main__":

    from sql.schema_introspect import introspect_schema

    schema = introspect_schema()

    examples = [
        "SELECT * FROM sales",
        "SELECT * FROM sales; DROP TABLE sales;",
        "DELETE FROM sales WHERE sale_id = 1",
        "SELECT region_name FROM regions WHERE region_name = 'تهران'",
        "SELECT made_up_column FROM sales",
        "SELECT * FROM made_up_table",
    ]

    for query in examples:
        result = validate_sql(query, schema)
        print(f"{result.ok!s:5} | {result.reason:30} | {query}")
