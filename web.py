"""
web.py
~~~~~~
Local Web UI server for the Text-to-SQL Query Generator.

Usage:
    python web.py              # serves on http://127.0.0.1:8000 and opens browser
    python web.py --port 8080  # custom port
    python web.py --no-browser # start server without auto-opening a browser tab
"""

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import threading
import urllib.parse
import webbrowser

import config
from src.agent  import answer_question_with_trace, MaxRetriesExceeded
from src.llm    import GeminiError
from src.schema import get_schema_details, preview_table

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
UI_DIR       = os.path.join(PROJECT_ROOT, "ui")


class TextToSQLHandler(BaseHTTPRequestHandler):
    """Serves the static UI and JSON / NDJSON API endpoints."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:
        # Clean concise request logging
        print(f"[web] {self.address_string()} - {format % args}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, rel_path: str) -> None:
        safe_path = os.path.normpath(os.path.join(UI_DIR, rel_path.lstrip("/")))
        if not safe_path.startswith(UI_DIR) or not os.path.isfile(safe_path):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        content_type, _ = mimetypes.guess_type(safe_path)
        if not content_type:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"

        with open(safe_path, "rb") as f:
            data = f.read()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ── Routes ────────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_file("index.html")
            return

        if path in {"/styles.css", "/app.js"}:
            self._serve_file(path)
            return

        if path == "/api/health":
            self._send_json({
                "ok": True,
                "model": config.GEMINI_MODEL,
                "thinking_level": config.THINKING_LEVEL,
                "db_type": config.DB_TYPE,
            })
            return

        if path == "/api/schema":
            try:
                details = get_schema_details()
                details["model"] = config.GEMINI_MODEL
                details["thinking_level"] = config.THINKING_LEVEL
                details["max_retries"] = config.MAX_RETRIES
                self._send_json(details)
            except Exception as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if path.startswith("/api/table/"):
            table_name = urllib.parse.unquote(path[len("/api/table/"):]).strip("/")
            try:
                data = preview_table(table_name, limit=8)
                self._send_json(data)
            except ValueError as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/query":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json({"error": "Invalid JSON request body."}, status=HTTPStatus.BAD_REQUEST)
            return

        question = str(body.get("question", "")).strip()
        simulate_error = bool(body.get("simulate_error", False))
        if not question:
            self._send_json({"error": "Please enter a question."}, status=HTTPStatus.BAD_REQUEST)
            return

        # Stream NDJSON progress events as each agentic step executes
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        write_lock = threading.Lock()

        def emit_line(payload: dict) -> None:
            line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            with write_lock:
                try:
                    self.wfile.write(line)
                    self.wfile.flush()
                except OSError:
                    pass

        try:
            result = answer_question_with_trace(
                question=question,
                simulate_error=simulate_error,
                on_event=emit_line,
                verbose=False,
            )
            emit_line({"type": "complete", "result": result})
        except (ValueError, MaxRetriesExceeded, EnvironmentError, FileNotFoundError, GeminiError) as e:
            emit_line({"type": "error", "error": str(e)})
        except Exception as e:
            emit_line({"type": "error", "error": f"Unexpected error: {e}"})


def run_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), TextToSQLHandler)
    url = f"http://{host}:{port}"
    print(f"\n🚀  Text-to-SQL Studio running at {url}")
    print(f"    Model: {config.GEMINI_MODEL}  ·  DB: {config.DB_TYPE}")
    print("    Press Ctrl-C to stop.\n")

    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server…")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Text-to-SQL Studio Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
