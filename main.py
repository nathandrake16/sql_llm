"""
main.py
~~~~~~~
Entry point for the Text-to-SQL Query Generator.

Usage:
    python main.py

Type 'exit' or 'quit' (or press Ctrl-C) to stop.
"""

from tabulate import tabulate

import config
from src.agent import answer_question, MaxRetriesExceeded
from src.llm   import GeminiError


BANNER = f"""
╔══════════════════════════════════════════════════════╗
║             Text-to-SQL  Query Generator             ║
║    Powered by Gemini API · {config.GEMINI_MODEL:<26}║
╚══════════════════════════════════════════════════════╝
Type a question in plain English, or 'exit' to quit.

Example questions:
  • Show me the top 5 highest-grossing products
  • Which customers placed more than 2 orders?
  • What is the total revenue per product category?
  • List all orders placed in March 2024
"""


def main() -> None:
    print(BANNER)

    while True:
        try:
            question = input("❓  Your question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye! 👋")
            break

        if not question:
            continue

        if question.lower() in {"exit", "quit", "q"}:
            print("Goodbye! 👋")
            break

        try:
            sql, columns, rows = answer_question(question)

            if not rows:
                print("\n✅  Query ran successfully but returned no rows.\n")
            else:
                print(f"\n✅  Results ({len(rows)} row{'s' if len(rows) != 1 else ''}):\n")
                print(tabulate(rows, headers=columns, tablefmt="rounded_outline"))
                print()

        except (ValueError, MaxRetriesExceeded) as e:
            print(f"\n❌  {e}\n")
        except (EnvironmentError, FileNotFoundError) as e:
            print(f"\n⚙️   {e}\n")
            break
        except GeminiError as e:
            print(f"\n🔌  {e}\n")
        except Exception as e:
            print(f"\n💥  Unexpected error: {e}\n")


if __name__ == "__main__":
    main()
