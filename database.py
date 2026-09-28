import os

import psycopg2
from dotenv import load_dotenv


load_dotenv()


DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

# The agent must never run queries as the superuser. All SQL generated
# from natural language goes through this least-privilege, read-only
# role instead (see db/migrations/001_readonly_role.sql).
AGENT_DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_AGENT_USER"),
    "password": os.getenv("DB_AGENT_PASSWORD"),
}


def execute_query(sql: str):

    connection = psycopg2.connect(**AGENT_DB_CONFIG)

    try:
        cursor = connection.cursor()

        cursor.execute(sql)

        columns = [desc[0] for desc in cursor.description]

        rows = cursor.fetchall()

        return columns, rows

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":

    sql = """
    SELECT
        COUNT(*) AS total_sales_records
    FROM sales;
    """

    columns, rows = execute_query(sql)

    print(columns)
    print(rows)