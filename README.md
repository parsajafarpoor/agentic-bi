# Agentic BI

A natural-language-to-SQL business intelligence agent for Persian-language questions, built around a local LLM (DeepSeek R1 via Ollama) with a validation layer that never trusts the model's SQL blindly.

Ask "درآمد کل ماه گذشته چقدر بود؟" and get back a real, safe query against Postgres — not a hallucinated number.

## Why this exists

LLMs are good at drafting SQL and bad at knowing when they're wrong. Most "chat with your database" demos skip the part where the model's output actually touches production data. This project is built around that gap:

- **A semantic layer** (`semantic/`) maps business terms (Persian aliases like «درآمد», «فروش») to real metric/dimension definitions, so the model gets told what "revenue" means instead of guessing a formula.
- **A SQL guard** (`sql/sql_guard.py`) is a deterministic, fail-closed gate the LLM's SQL must pass before execution: keyword allowlist (SELECT/WITH only, no DDL/DML), structural validation against the real schema via `sqlglot`, and an enforced row cap. It never asks another LLM to "check" the SQL — that just repeats the same trust problem with extra latency.
- **A least-privilege DB role** (`db/migrations/001_readonly_role.sql`) — the agent never connects with the same credentials used to seed data.
- **A golden-dataset regression harness** (`eval/`) compares the agent's generated SQL against live-executed reference queries, not hand-typed expected numbers, so the eval suite doesn't rot when the synthetic data changes.

## How it works

```
question (fa) → semantic.resolver (match metrics/dims) → llm.ask_deepseek (generate SQL)
             → sql.sql_guard (validate) → database.execute_query → answer
```

`agent.py` also strips DeepSeek R1's `<think>...</think>` reasoning blocks and narration text before anything reaches Postgres, and includes a repair step for SQL that fails validation on the first pass.

## Stack

Python · PostgreSQL (`psycopg2`) · Ollama (`deepseek-r1:7b`) · `sqlglot` for SQL parsing/validation · `Faker` for synthetic data · `pandas`/`numpy` · `pyyaml` for the semantic layer and eval dataset

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in your Postgres credentials
psql -f db/migrations/001_readonly_role.sql   # create the least-privilege role
python generate_data.py     # seed synthetic sales data
python -m eval.run_eval     # regression-test SQL generation against golden_dataset.yaml
```

Requires a local [Ollama](https://ollama.com) instance running `deepseek-r1:7b` (or edit `MODEL` in `llm.py` for a different model).

## Layout

```
agent.py             orchestrates the question → SQL → answer pipeline
llm.py               talks to the local Ollama model
database.py          Postgres connection (agent role vs. seed/superuser role)
generate_data.py     synthetic sales dataset generator (Faker)
semantic/            business metric/dimension definitions + Persian-alias resolver
sql/                 schema introspection + the SQL validation guard
db/migrations/       least-privilege role setup
eval/                golden-dataset regression harness
```
