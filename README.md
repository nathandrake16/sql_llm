# Text-to-SQL Query Generator

A Gemini-powered tool that translates natural language questions into executable SQL queries, featuring an agentic self-correction loop.

## Stack

- **LLM**: [Gemini API](https://ai.google.dev) via `google-genai` (Interactions API with `gemini-3.5-flash-lite`)
- **Database**: SQLite (sample e-commerce DB included; swap for PostgreSQL easily)
- **Language**: Python 3.10+

## Project Structure

```
sql_llm/
├── db/
│   └── seed.py          # Creates and seeds the sample SQLite database
├── src/
│   ├── schema.py        # Extracts DB schema into a prompt-ready string
│   ├── prompt.py        # System instructions, prompt builder & correction prompt
│   ├── llm.py           # Calls the Gemini Interactions API
│   └── agent.py         # Validation loop: runs SQL, catches errors, self-corrects
├── main.py              # Interactive CLI entry point
├── web.py               # Local Web UI server (Text-to-SQL Studio)
├── ui/                  # Frontend HTML, CSS, and JS for the Web UI
├── config.py            # Settings (API key/model, thinking level, DB path, retries)
├── requirements.txt
└── README.md
```

## Quickstart

### 1. Set your Gemini API Key
Create a free API key at [Google AI Studio](https://aistudio.google.com/apikey), then copy `.env.example` to `.env` and add your key:

```env
GEMINI_API_KEY=your_api_key_here
```

*(`.env` is gitignored so your key won't be committed. You can also set `$env:GEMINI_API_KEY` in PowerShell.)*

### 2. Install Python dependencies
```bash
pip install -U -r requirements.txt
```

### 3. Create the sample database
```bash
python db/seed.py
```

### 4. Run the Web UI (recommended) or CLI
```bash
# Web UI (opens http://127.0.0.1:8000 with Schema/ER explorer, pipeline trace & charts)
python web.py

# Or interactive terminal CLI
python main.py
```

Try asking:
- *"Show me the top 5 highest-grossing products"*
- *"Which customers placed more than 2 orders?"*
- *"What is the total revenue per product category?"*
- *"List all orders placed in March 2024"*

## How It Works

```
User Question
      │
      ▼
Schema Extractor  ──►  schema.py pulls table/column/FK info from SQLite
      │
      ▼
Prompt Builder    ──►  prompt.py injects dialect + schema + question
      │
      ▼
Gemini API Call   ──►  llm.py calls client.interactions.create()
      │
      ▼
SQL Validator     ──►  agent.py executes the SQL against the DB
      │
   ┌──┴──┐
   │     │
Success  Error ──► Chain previous_interaction_id + error trace → retry (up to N times)
   │
   ▼
Print Results
```

## Swapping to PostgreSQL

1. Uncomment `psycopg2-binary` in `requirements.txt` and run `pip install -r requirements.txt`.
2. In `config.py`, set `DB_TYPE = "postgres"` and update `PG_DSN`.

Both `src/schema.py` and `src/agent.py` switch automatically.

## Changing the Model or Thinking Level

Edit `config.py`:
```python
GEMINI_MODEL   = "gemini-3.5-flash-lite"  # or "gemini-3.8-flash", "gemini-4-argon"
THINKING_LEVEL = "low"                    # "low" (faster) | "medium" (default) | "high"
```
