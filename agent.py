import re

from llm import ask_deepseek
from database import execute_query
from sql.schema_introspect import introspect_schema
from sql.sql_guard import validate_sql
from semantic.resolver import resolve_metrics


# DeepSeek R1 is a reasoning model: it often wraps its scratch thinking in
# <think>...</think> before the actual answer. Left in, that text would be
# sent straight to Postgres and blow up as a syntax error.
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Even without ``` fences, the model often narrates ("Here's the fixed
# query:" ... "The only change made was..."). Anchor on the first
# WITH/SELECT keyword and cut at the first semicolon to isolate the
# actual statement from surrounding prose.
SQL_START = re.compile(r"\b(WITH|SELECT)\b", re.IGNORECASE)


# ============================================================
# CLEAN SQL
# ============================================================

def clean_sql(sql):

    sql = THINK_BLOCK.sub("", sql)

    sql = sql.replace("```sql", "")
    sql = sql.replace("```SQL", "")
    sql = sql.replace("```", "")

    match = SQL_START.search(sql)
    if match:
        sql = sql[match.start():]

    if ";" in sql:
        sql = sql.split(";")[0]

    sql = sql.strip()

    return sql


# ============================================================
# GENERATE SQL
# ============================================================

def generate_sql(question, schema_text):

    semantic_context = resolve_metrics(question).render()

    prompt = f"""
You are an expert PostgreSQL Business Intelligence SQL generator.

Convert the user's business question into ONE correct PostgreSQL
SELECT query.

DATABASE SCHEMA:

{schema_text}

{semantic_context}

Use the metric expressions and dimension join paths above exactly as
defined - do not invent a different formula for a metric that is
already defined (e.g. "profit" must use the profit expression above,
not something you derive yourself).

IMPORTANT BUSINESS RULES:

1. Return ONLY SQL.
2. Never return markdown.
3. Never return ```sql.
4. Never explain your answer.
5. Only generate SELECT statements.
6. Never use INSERT, UPDATE, DELETE, DROP, ALTER or TRUNCATE.
7. Use ONLY tables and columns that exist in the schema.
8. If the requested information belongs to another table,
   use the correct JOIN.
9. Always use table aliases when multiple tables are involved.
10. Every selected non-aggregated column must appear in GROUP BY.
11. Do not reference a table unless it is included in FROM or JOIN.
12. Do not add unnecessary tables or conditions.
13. For "profit", calculate:

    SUM(s.total_amount - s.total_cost)

14. For "revenue" or "sales", calculate:

    SUM(s.total_amount)

15. For "units sold", calculate:

    SUM(s.quantity)

16. For manager analysis, remember:

    sales.manager_id = sales_managers.manager_id

17. For product analysis, remember:

    sales.product_id = products.product_id

18. For region analysis:

    sales.manager_id
    -> sales_managers.manager_id
    -> regions.region_id

19. Always use LIMIT when the user asks for
    "highest", "lowest", "best", "worst", "top" or "bottom".

20. Make sure the final SQL is valid PostgreSQL.

21. To filter or group by year/month, use EXTRACT(YEAR FROM column)
    or EXTRACT(MONTH FROM column) — EXTRACT takes FROM, not a comma.
    Example: EXTRACT(YEAR FROM s.sale_date) = 2025
    Do NOT write extract('year', s.sale_date) — that is invalid syntax.

USER QUESTION:

{question}
"""

    sql = ask_deepseek(prompt)

    return clean_sql(sql)


# ============================================================
# REPAIR SQL
# ============================================================

def repair_sql(question, bad_sql, error_message, schema_text):

    semantic_context = resolve_metrics(question).render()

    prompt = f"""
You are an expert PostgreSQL SQL debugging agent.

The user asked:

{question}

The previously generated SQL was:

{bad_sql}

PostgreSQL returned this error:

{error_message}

DATABASE SCHEMA:

{schema_text}

{semantic_context}

Your task is to FIX the SQL query.

IMPORTANT RULES:

1. Return ONLY the corrected SQL.
2. Do not use markdown.
3. Do not use ```sql.
4. Do not explain anything.
5. Only return one SELECT statement.
6. Never use INSERT, UPDATE, DELETE, DROP, ALTER or TRUNCATE.
7. Use ONLY tables and columns from the schema.
8. If a column belongs to another table, add the correct JOIN.
9. Use table aliases.
10. Make sure all non-aggregated selected columns are in GROUP BY.
11. Do not add unrelated tables.
12. Do not invent columns.
13. Do not invent tables.
15. To filter or group by year/month, use EXTRACT(YEAR FROM column) or
    EXTRACT(MONTH FROM column) — EXTRACT takes FROM, not a comma. Do
    NOT write extract('year', column) — that is invalid syntax.
14. Preserve the original business intent of the question.

Useful relationships:

sales.manager_id = sales_managers.manager_id

sales.product_id = products.product_id

sales_managers.region_id = regions.region_id

sales.customer_id = customers.customer_id

USER QUESTION:

{question}

BAD SQL:

{bad_sql}

POSTGRESQL ERROR:

{error_message}

Return ONLY the corrected PostgreSQL SQL.
"""

    sql = ask_deepseek(prompt)

    return clean_sql(sql)


# ============================================================
# FINAL ANSWER
# ============================================================

def generate_final_answer(question, sql, columns, rows):

    result_text = f"""
Columns:
{columns}

Rows:
{rows}
"""

    prompt = f"""
You are a professional Business Intelligence analyst.

The user asked:

{question}

The following SQL query was executed:

{sql}

The database returned:

{result_text}

Answer the original question using ONLY the database result.

RULES:

1. Answer in Persian.
2. Do not invent numbers.
3. Do not change the database result.
4. Do not make unsupported assumptions.
5. Be concise and clear.
6. If there are multiple results, identify the important findings.
7. If the result contains a sales or profit amount,
   describe it as تومان.
8. If there is no result, clearly say that no data was found.
9. Do not mention SQL unless necessary.
10. Do not describe your internal reasoning.
"""

    answer = ask_deepseek(prompt)

    return answer.strip()


# ============================================================
# MAIN AGENT
# ============================================================

def run_agent(question):

    print("\n" + "=" * 60)
    print("QUESTION")
    print("=" * 60)

    print(question)

    # --------------------------------------------------------
    # Read the real schema (never trust a hardcoded string)
    # --------------------------------------------------------

    schema = introspect_schema()
    schema_text = schema.render()

    # --------------------------------------------------------
    # Generate initial SQL
    # --------------------------------------------------------

    print("\nGenerating SQL...\n")

    sql = generate_sql(question, schema_text)

    # --------------------------------------------------------
    # Maximum 3 attempts
    # --------------------------------------------------------

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

        print("=" * 60)
        print(f"SQL ATTEMPT {attempt}")
        print("=" * 60)

        print(sql)

        # ----------------------------------------------------
        # Validate SQL deterministically before it ever
        # touches the database (allowlist + schema check)
        # ----------------------------------------------------

        validation = validate_sql(sql, schema)

        if not validation.ok:

            error_message = f"SQL rejected by validator: {validation.reason}"

            print("=" * 60)
            print("SQL VALIDATION ERROR")
            print("=" * 60)

            print(error_message)

            if attempt >= max_attempts:

                print("\nAgent failed after 3 SQL attempts.")

                return None

            print("\nRepairing SQL with DeepSeek...\n")

            sql = repair_sql(
                question,
                sql,
                error_message,
                schema_text
            )

            continue

        sql = validation.sql

        # ----------------------------------------------------
        # Execute SQL
        # ----------------------------------------------------

        print("\nExecuting SQL...\n")

        try:

            columns, rows = execute_query(sql)

        except Exception as error:

            error_message = str(error)

            print("=" * 60)
            print("SQL EXECUTION ERROR")
            print("=" * 60)

            print(error_message)

            # -----------------------------------------------
            # No more attempts
            # -----------------------------------------------

            if attempt >= max_attempts:

                print("\nAgent failed after 3 SQL attempts.")

                return None

            # -----------------------------------------------
            # Repair SQL
            # -----------------------------------------------

            print("\nRepairing SQL with DeepSeek...\n")

            sql = repair_sql(
                question,
                sql,
                error_message,
                schema_text
            )

            continue

        # ----------------------------------------------------
        # Successful SQL execution
        # ----------------------------------------------------

        print("=" * 60)
        print("DATABASE RESULT")
        print("=" * 60)

        print(columns)
        print(rows)

        # ----------------------------------------------------
        # Generate final answer
        # ----------------------------------------------------

        print("\nGenerating final answer...\n")

        final_answer = generate_final_answer(
            question,
            sql,
            columns,
            rows
        )

        print("=" * 60)
        print("FINAL ANSWER")
        print("=" * 60)

        print(final_answer)

        return final_answer

    return None


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    question = input("\nAsk a business question: ")

    run_agent(question)