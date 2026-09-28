"""Regression harness for SQL generation.

Runs every case in golden_dataset.yaml through the same SQL-generation +
validation + repair path as agent.run_agent(), but stops before the
second (answer-writing) LLM call - this measures SQL correctness, which
is the thing that actually changes when you edit prompts, the semantic
layer, or the validator. Numbers are compared against reference_sql
executed live, not hand-typed expected values, so the dataset doesn't
rot when generate_data.py's output changes.

Usage:
    python -m eval.run_eval
"""

import sys
import time
from pathlib import Path

import yaml

from agent import generate_sql, repair_sql, clean_sql
from database import execute_query
from sql.schema_introspect import introspect_schema
from sql.sql_guard import validate_sql

DATASET_PATH = Path(__file__).parent / "golden_dataset.yaml"
MAX_ATTEMPTS = 3
NUMERIC_TOLERANCE = 0.01  # 1% relative tolerance for float comparisons


def _load_cases():
    with open(DATASET_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["cases"]


def _rows_match(expected, actual):
    if expected is None or actual is None:
        return expected == actual

    if len(expected) != len(actual):
        return False

    def row_match(exp_row, act_row):
        if len(exp_row) != len(act_row):
            return False
        for exp_val, act_val in zip(exp_row, act_row):
            if isinstance(exp_val, (int, float)) and isinstance(act_val, (int, float)):
                if exp_val == 0:
                    if abs(act_val) > NUMERIC_TOLERANCE:
                        return False
                elif abs(act_val - exp_val) / abs(exp_val) > NUMERIC_TOLERANCE:
                    return False
            elif exp_val != act_val:
                return False
        return True

    # Order-insensitive compare (GROUP BY order isn't guaranteed unless
    # the reference query specifies ORDER BY).
    remaining = list(actual)
    for exp_row in expected:
        match_index = next(
            (i for i, act_row in enumerate(remaining) if row_match(exp_row, act_row)),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)

    return True


def run_sql_pipeline(question, schema, schema_text):
    """Mirrors agent.run_agent()'s SQL loop without the answer-writing call."""

    sql = generate_sql(question, schema_text)

    for attempt in range(1, MAX_ATTEMPTS + 1):

        validation = validate_sql(sql, schema)

        if not validation.ok:
            if attempt >= MAX_ATTEMPTS:
                return None, f"validator_rejected: {validation.reason}"
            sql = repair_sql(question, sql, f"SQL rejected by validator: {validation.reason}", schema_text)
            continue

        sql = validation.sql

        try:
            columns, rows = execute_query(sql)
            return sql, (columns, rows)
        except Exception as error:
            if attempt >= MAX_ATTEMPTS:
                return None, f"execution_error: {error}"
            sql = repair_sql(question, sql, str(error), schema_text)

    return None, "max_attempts_exceeded"


def run_eval():

    schema = introspect_schema()
    schema_text = schema.render()

    cases = _load_cases()

    results = []

    for case in cases:

        case_id = case["id"]
        category = case["category"]
        question = case["question_fa"]
        expect = case.get("expect")

        print(f"[{category}] {case_id} :: {question}")

        start = time.time()

        if expect in ("rejection", "clarification"):
            # Adversarial / ambiguous cases: the agent must NOT produce
            # and execute SQL. Phase 1 covers rejection (the validator
            # blocks it); clarification is a Phase 3 capability, so we
            # report those as not-yet-implemented rather than failing
            # the whole run.
            if expect == "clarification":
                results.append({"id": case_id, "status": "not_implemented", "reason": "clarification flow is Phase 3"})
                print("  -> SKIP (clarification not implemented yet)\n")
                continue

            sql, outcome = run_sql_pipeline(question, schema, schema_text)
            passed = sql is None
            results.append({"id": case_id, "status": "pass" if passed else "fail", "detail": outcome})
            print(f"  -> {'PASS' if passed else 'FAIL'} (expected rejection) [{time.time()-start:.1f}s]\n")
            continue

        # Normal case: compare against reference_sql ground truth.
        ref_columns, ref_rows = execute_query(case["reference_sql"])

        sql, outcome = run_sql_pipeline(question, schema, schema_text)

        if sql is None:
            results.append({"id": case_id, "status": "fail", "detail": f"no SQL produced: {outcome}"})
            print(f"  -> FAIL ({outcome}) [{time.time()-start:.1f}s]\n")
            continue

        _, rows = outcome
        passed = _rows_match(ref_rows, rows)

        results.append({
            "id": case_id,
            "status": "pass" if passed else "fail",
            "generated_sql": sql,
            "expected": ref_rows,
            "actual": rows,
        })

        print(f"  -> {'PASS' if passed else 'FAIL'} [{time.time()-start:.1f}s]")
        if not passed:
            print(f"     SQL: {sql}")
            print(f"     expected: {ref_rows}")
            print(f"     actual:   {rows}")
        print()

    total = len([r for r in results if r["status"] in ("pass", "fail")])
    passed_count = len([r for r in results if r["status"] == "pass"])
    skipped = len([r for r in results if r["status"] == "not_implemented"])

    print("=" * 60)
    print(f"RESULT: {passed_count}/{total} passed ({skipped} skipped, not yet implemented)")
    print("=" * 60)

    return results


if __name__ == "__main__":

    results = run_eval()

    failed = [r for r in results if r["status"] == "fail"]

    sys.exit(1 if failed else 0)
