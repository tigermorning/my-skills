"""Tiny notes API. POST /notes with JSON {"title": str, "body": str}. GET /notes lists them."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB = Path(__file__).with_name("notes.json")

def load():
    return json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else []

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, load())

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            note = json.loads(raw.decode("utf-8"))
            assert isinstance(note.get("title"), str)
        except Exception:
            return self._send(400, {"detail": "There was an error parsing the body"})
        notes = load()
        notes.append({"title": note["title"], "body": note.get("body", "")})
        DB.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
        self._send(201, {"ok": True, "id": len(notes)})

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
