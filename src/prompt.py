"""
src/prompt.py
~~~~~~~~~~~~~
Assembles the prompt components sent to the Gemini Interactions API:

  1. SYSTEM_PROMPT            — rigid role instructions; bans prose & markdown
  2. build_prompt()           — injects DB dialect + schema + user question
  3. build_correction_prompt()— feeds DB error trace back for self-correction
"""

SYSTEM_PROMPT = """\
You are a SQL query generator. Your sole purpose is to convert a natural \
language question into a single, executable SQL query.

Rules you MUST follow:
- Output ONLY the raw SQL query. No explanations, no markdown code fences, \
no commentary, no apologies.
- Only generate read-only SELECT queries (or CTEs starting with WITH ... SELECT). \
Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or CREATE statements.
- Use only the tables and columns that exist in the schema provided.
- Never use SELECT *; always name the specific columns you need.
- Always use table aliases when joining two or more tables (e.g. o.id).
- For aggregations, always provide a meaningful column alias (e.g. AS total_revenue).
- Terminate the query with a semicolon.
- If you cannot answer the question from the given schema, output exactly: \
CANNOT_ANSWER\
"""


def build_prompt(schema: str, question: str, dialect: str = "SQLite") -> str:
    """
    Combine the extracted database schema and the user's natural language
    question into the grounded user input string.
    """
    return (
        f"SQL Dialect: {dialect}\n\n"
        "Database schema:\n"
        "```\n"
        f"{schema}\n"
        "```\n\n"
        f"Question: {question}"
    )


def build_correction_prompt(bad_sql: str, error: str) -> str:
    """
    Build the follow-up message sent when the generated SQL fails at execution.
    Gemini retains the schema, question, and previous SQL via
    `previous_interaction_id`, so we only need to send the failed query and
    database error trace.
    """
    return (
        "The SQL query you generated caused a database error:\n\n"
        f"Query:\n{bad_sql}\n\n"
        f"Error:\n{error}\n\n"
        "Fix the query and output ONLY the corrected raw SQL query. "
        "No explanations and no markdown code fences."
    )
