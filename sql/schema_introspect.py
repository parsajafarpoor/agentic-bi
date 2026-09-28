"""Reads the real database schema instead of trusting a hardcoded string.

Keeps sql_guard.py honest: a table/column is only "known" if it actually
exists in agentic_bi right now.
"""

from dataclasses import dataclass, field

import psycopg2

from database import AGENT_DB_CONFIG


@dataclass
class Schema:
    tables: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)
    columns_by_table: dict[str, set[str]] = field(default_factory=dict)

    def render(self) -> str:
        lines = ["Database: agentic_bi", ""]
        for table in sorted(self.columns_by_table):
            lines.append(table)
            for column in sorted(self.columns_by_table[table]):
                lines.append(f"- {column}")
            lines.append("")
        return "\n".join(lines)


def introspect_schema() -> Schema:
    connection = psycopg2.connect(**AGENT_DB_CONFIG)

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
            """
        )

        schema = Schema()

        for table_name, column_name in cursor.fetchall():
            schema.tables.add(table_name)
            schema.columns.add(column_name)
            schema.columns_by_table.setdefault(table_name, set()).add(column_name)

        return schema

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":

    schema = introspect_schema()

    print(schema.render())
