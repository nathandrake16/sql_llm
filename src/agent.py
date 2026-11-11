"""
src/agent.py
~~~~~~~~~~~~
The agentic validation loop — the core of the project.

Flow
----
1. Extract schema & build the initial grounded prompt.
2. Call Gemini via the Interactions API → receive raw SQL + interaction_id.
3. Execute the SQL against the database (read-only).
4. If it throws an error, chain `previous_interaction_id` and feed the error
   trace back to Gemini so it can self-correct (up to config.MAX_RETRIES).
5. Return results + full execution trace on success, or raise after retries.
"""

import os
import re
import sqlite3
import sys
import time
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from src.llm    import call_llm, GeminiError
from src.prompt import SYSTEM_PROMPT, build_prompt, build_correction_prompt
from src.schema import get_schema_details, format_schema, resolve_sqlite_path


# ── Database execution ─────────────────────────────────────────────────────────

def _strip_leading_sql_comments(sql: str) -> str:
    """Remove leading whitespace and SQL comments (-- or /* ... */)."""
    s = sql.lstrip()
    while s:
        if s.startswith("--"):
            newline = s.find("\n")
            s = s[newline + 1:].lstrip() if newline != -1 else ""
        elif s.startswith("/*"):
            end = s.find("*/")
            s = s[end + 2:].lstrip() if end != -1 else ""
        else:
            break
    return s


def _ensure_read_only(sql: str) -> None:
    """Reject non-SELECT statements before executing against the database."""
    cleaned = _strip_leading_sql_comments(sql)
    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        raise ValueError(
            "Only read-only SELECT or WITH ... SELECT queries are allowed."
        )


def _run_sql(sql: str) -> tuple[list[str], list[tuple]]:
    """
    Execute a read-only SQL string and return (column_names, rows).
    Raises sqlite3.Error / psycopg2.Error / ValueError on failure.
    """
    _ensure_read_only(sql)

    if config.DB_TYPE == "sqlite":
        db_path = resolve_sqlite_path()
        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"SQLite database not found at: {db_path}\n"
                "Run `python db/seed.py` first."
            )
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description] if cur.description else []
            return columns, [tuple(r) for r in rows]
        finally:
            con.close()

    elif config.DB_TYPE == "postgres":
        try:
            import psycopg2
        except ImportError:
            raise ImportError("psycopg2-binary is required. Run: pip install psycopg2-binary")
        con = psycopg2.connect(config.PG_DSN)
        con.set_session(readonly=True)
        cur = con.cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description] if cur.description else []
            return columns, rows
        finally:
            cur.close()
            con.close()

    else:
        raise ValueError(f"Unknown DB_TYPE: {config.DB_TYPE!r}")


# ── Public API ─────────────────────────────────────────────────────────────────

class MaxRetriesExceeded(Exception):
    """Raised when the LLM fails to produce valid SQL after MAX_RETRIES retries."""


def answer_question_with_trace(
    question: str,
    simulate_error: bool = False,
    on_event: Callable[[dict], None] | None = None,
    verbose: bool = False,
) -> dict:
    """
    Run the full Text-to-SQL agentic loop and return a structured trace dict
    containing schema, prompts, all LLM attempts, timing, SQL, columns, and rows.
    """
    def emit(event: dict) -> None:
        if on_event is not None:
            on_event(event)

    overall_start = time.perf_counter()

    # ── Stage 1: Schema Extraction ────────────────────────────────────────────
    t0 = time.perf_counter()
    details = get_schema_details()
    schema  = format_schema(details)
    dialect = details["dialect"]
    schema_ms = round((time.perf_counter() - t0) * 1000, 1)

    emit({
        "type": "schema",
        "dialect": dialect,
        "table_count": len(details["tables"]),
        "schema": schema,
        "duration_ms": schema_ms,
    })

    # ── Stage 2: Grounded Prompt Assembly ─────────────────────────────────────
    user_input = build_prompt(schema, question, dialect=dialect)
    emit({
        "type": "prompt",
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_input,
        "model": config.GEMINI_MODEL,
        "thinking_level": config.THINKING_LEVEL,
    })

    interaction_id = None
    total_attempts = 1 + config.MAX_RETRIES
    sql            = ""
    attempts: list[dict] = []

    for attempt in range(1, total_attempts + 1):
        # ── Stage 3: Gemini API Call ──────────────────────────────────────────
        if verbose:
            print(f"\n🤖  Gemini call ({attempt}/{total_attempts})…", end=" ", flush=True)
        emit({
            "type": "llm_start",
            "attempt": attempt,
            "total_attempts": total_attempts,
            "chained_from": interaction_id,
        })

        t_llm = time.perf_counter()
        sql, interaction_id = call_llm(
            user_input=user_input,
            system_instruction=SYSTEM_PROMPT,
            previous_interaction_id=interaction_id,
        )
        llm_ms = round((time.perf_counter() - t_llm) * 1000, 1)

        if verbose:
            print("done.")

        emit({
            "type": "llm_done",
            "attempt": attempt,
            "sql": sql,
            "interaction_id": interaction_id,
            "duration_ms": llm_ms,
        })

        if sql.strip().upper() == "CANNOT_ANSWER":
            raise ValueError(
                "The model determined it cannot answer this question from the given schema."
            )

        if verbose:
            print(f"\n📝  Generated SQL:\n{sql}\n")

        # ── Stage 4: Execute & Validate ───────────────────────────────────────
        emit({"type": "sql_start", "attempt": attempt, "sql": sql})
        t_sql = time.perf_counter()

        try:
            if simulate_error and attempt == 1:
                # Deliberately trigger a realistic DB error on attempt 1 so the
                # user can observe Step 5 (agentic self-correction) live.
                raise sqlite3.OperationalError(
                    "Simulated DB error: no such column: p.total_sales "
                    "(verify exact column names against the schema and fix)"
                )

            columns, rows = _run_sql(sql)
            sql_ms = round((time.perf_counter() - t_sql) * 1000, 1)

            attempts.append({
                "attempt": attempt,
                "sql": sql,
                "interaction_id": interaction_id,
                "status": "success",
                "error": None,
                "llm_ms": llm_ms,
                "sql_ms": sql_ms,
            })

            emit({
                "type": "sql_done",
                "attempt": attempt,
                "row_count": len(rows),
                "duration_ms": sql_ms,
            })

            return {
                "question": question,
                "dialect": dialect,
                "model": config.GEMINI_MODEL,
                "schema": schema,
                "system_prompt": SYSTEM_PROMPT,
                "initial_user_prompt": build_prompt(schema, question, dialect=dialect),
                "sql": sql,
                "columns": columns,
                "rows": [list(r) for r in rows],
                "attempts": attempts,
                "total_duration_ms": round((time.perf_counter() - overall_start) * 1000, 1),
            }

        except Exception as db_error:
            sql_ms = round((time.perf_counter() - t_sql) * 1000, 1)
            error_msg = str(db_error)

            attempts.append({
                "attempt": attempt,
                "sql": sql,
                "interaction_id": interaction_id,
                "status": "error",
                "error": error_msg,
                "llm_ms": llm_ms,
                "sql_ms": sql_ms,
            })

            if verbose:
                print(f"⚠️   DB error (attempt {attempt}/{total_attempts}): {error_msg}")

            emit({
                "type": "sql_error",
                "attempt": attempt,
                "error": error_msg,
                "duration_ms": sql_ms,
            })

            if attempt == total_attempts:
                break

            # ── Stage 5: Self-Correction via Interaction Chaining ─────────────
            if verbose:
                print("🔄  Feeding error back to Gemini for self-correction…")
            user_input = build_correction_prompt(sql, error_msg)
            emit({
                "type": "retrying",
                "from_attempt": attempt,
                "to_attempt": attempt + 1,
                "correction_prompt": user_input,
                "previous_interaction_id": interaction_id,
            })

    raise MaxRetriesExceeded(
        f"Failed to generate valid SQL after {total_attempts} attempts.\n"
        f"Last SQL attempted:\n{sql}"
    )


def answer_question(question: str) -> tuple[str, list[str], list[tuple]]:
    """
    CLI-friendly wrapper returning (final_sql, columns, rows).
    """
    result = answer_question_with_trace(question, verbose=True)
    return (
        result["sql"],
        result["columns"],
        [tuple(r) for r in result["rows"]],
    )
