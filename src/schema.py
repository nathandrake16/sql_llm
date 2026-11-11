"""
src/schema.py
~~~~~~~~~~~~~
Extracts the database schema as both:
  - get_schema()         -> compact prompt-ready text string for the LLM
  - get_schema_details() -> structured dict (tables, columns, PK/FK, row counts) for the Web UI
  - preview_table()      -> sample rows for a table (read-only)

Postgres support: set DB_TYPE = "postgres" and PG_DSN in config.py.
"""

import os
import sqlite3
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
import config


def resolve_sqlite_path() -> str:
    """Resolve SQLITE_PATH relative to the project root if not already absolute."""
    if os.path.isabs(config.SQLITE_PATH):
        return config.SQLITE_PATH
    return os.path.join(PROJECT_ROOT, config.SQLITE_PATH)


def _sqlite_details(db_path: str) -> dict:
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"SQLite database not found at: {db_path}\n"
            "Run `python db/seed.py` first to create and seed the sample database."
        )

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    try:
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [row[0] for row in cur.fetchall()]

        tables: list[dict] = []
        for table in table_names:
            cur.execute(f'PRAGMA table_info("{table}")')
            raw_cols = cur.fetchall()

            cur.execute(f'PRAGMA foreign_key_list("{table}")')
            fks = {row[3]: {"table": row[2], "column": row[4]} for row in cur.fetchall()}

            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            row_count = cur.fetchone()[0]

            columns = []
            for _, name, col_type, notnull, _, is_pk in raw_cols:
                columns.append({
                    "name": name,
                    "type": col_type or "TEXT",
                    "pk": bool(is_pk),
                    "nullable": not bool(notnull),
                    "fk": fks.get(name),
                })

            tables.append({
                "name": table,
                "row_count": row_count,
                "columns": columns,
            })

        return {"dialect": "SQLite", "db_name": os.path.basename(db_path), "tables": tables}
    finally:
        con.close()


def _postgres_details(dsn: str) -> dict:
    try:
        import psycopg2
    except ImportError:
        raise ImportError("psycopg2 is required for Postgres. Run: pip install psycopg2-binary")

    con = psycopg2.connect(dsn)
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        table_names = [row[0] for row in cur.fetchall()]

        tables: list[dict] = []
        for table in table_names:
            cur.execute("""
                SELECT c.column_name, c.data_type, c.is_nullable,
                       CASE WHEN kcu.column_name IS NOT NULL THEN TRUE ELSE FALSE END AS pk,
                       ccu.table_name AS fk_table, ccu.column_name AS fk_col
                FROM information_schema.columns c
                LEFT JOIN information_schema.key_column_usage kcu
                       ON kcu.table_schema = c.table_schema
                      AND kcu.table_name = c.table_name
                      AND kcu.column_name = c.column_name
                      AND kcu.constraint_name IN (
                            SELECT constraint_name FROM information_schema.table_constraints
                            WHERE constraint_type = 'PRIMARY KEY'
                              AND table_schema = c.table_schema
                              AND table_name = c.table_name
                          )
                LEFT JOIN information_schema.referential_constraints rc
                       ON rc.constraint_schema = c.table_schema
                      AND rc.constraint_name IN (
                            SELECT constraint_name FROM information_schema.key_column_usage
                            WHERE table_schema = c.table_schema
                              AND table_name = c.table_name
                              AND column_name = c.column_name
                          )
                LEFT JOIN information_schema.key_column_usage ccu
                       ON ccu.constraint_schema = rc.unique_constraint_schema
                      AND ccu.constraint_name = rc.unique_constraint_name
                WHERE c.table_name = %s AND c.table_schema = 'public'
                ORDER BY c.ordinal_position
            """, (table,))

            columns = []
            for name, col_type, is_nullable, pk, fk_table, fk_col in cur.fetchall():
                columns.append({
                    "name": name,
                    "type": col_type,
                    "pk": bool(pk),
                    "nullable": is_nullable == "YES",
                    "fk": {"table": fk_table, "column": fk_col} if fk_table else None,
                })

            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            row_count = cur.fetchone()[0]

            tables.append({
                "name": table,
                "row_count": row_count,
                "columns": columns,
            })

        return {"dialect": "PostgreSQL", "db_name": "public", "tables": tables}
    finally:
        cur.close()
        con.close()


# ── public API ─────────────────────────────────────────────────────────────────

def get_schema_details() -> dict:
    """Return structured schema metadata for the configured database."""
    if config.DB_TYPE == "sqlite":
        return _sqlite_details(resolve_sqlite_path())
    elif config.DB_TYPE == "postgres":
        return _postgres_details(config.PG_DSN)
    else:
        raise ValueError(f"Unknown DB_TYPE: {config.DB_TYPE!r}. Use 'sqlite' or 'postgres'.")


def format_schema(details: dict) -> str:
    """Format structured schema metadata into a compact prompt-ready string."""
    lines: list[str] = []
    for table in details["tables"]:
        lines.append(f"TABLE {table['name']}")
        for col in table["columns"]:
            tags: list[str] = []
            if col["pk"]:
                tags.append("PK")
            if col["fk"]:
                tags.append(f"FK → {col['fk']['table']}({col['fk']['column']})")
            suffix = "  " + ", ".join(tags) if tags else ""
            lines.append(f"  {col['name']:<20} {col['type']}{suffix}")
        lines.append("")
    return "\n".join(lines).strip()


def get_schema() -> str:
    """Return the full schema as a formatted string, based on config.DB_TYPE."""
    return format_schema(get_schema_details())


def preview_table(table_name: str, limit: int = 5) -> dict:
    """Return sample rows for a valid table name (strictly allowlisted against schema)."""
    details = get_schema_details()
    valid_tables = {t["name"] for t in details["tables"]}
    if table_name not in valid_tables:
        raise ValueError(f"Unknown table: {table_name!r}")

    safe_limit = max(1, min(int(limit), 50))

    if config.DB_TYPE == "sqlite":
        db_path = resolve_sqlite_path()
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = con.cursor()
        try:
            cur.execute(f'SELECT * FROM "{table_name}" LIMIT ?', (safe_limit,))
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()]
            return {"table": table_name, "columns": columns, "rows": rows}
        finally:
            con.close()
    elif config.DB_TYPE == "postgres":
        import psycopg2
        con = psycopg2.connect(config.PG_DSN)
        cur = con.cursor()
        try:
            cur.execute(f'SELECT * FROM "{table_name}" LIMIT %s', (safe_limit,))
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()]
            return {"table": table_name, "columns": columns, "rows": rows}
        finally:
            cur.close()
            con.close()
    else:
        raise ValueError(f"Unknown DB_TYPE: {config.DB_TYPE!r}")


if __name__ == "__main__":
    print(get_schema())
