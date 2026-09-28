"""메모판: 메모를 적고, 찾고, 고정하고, 지우는 작은 웹앱.

실행: python app.py <포트>
"""
import csv
import io
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
DATA = HERE / "memos.json"


def load_env():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def read_memos():
    if not DATA.exists():
        return [
            {"id": 1, "text": "장보기: 두부, 대파", "pinned": True},
            {"id": 2, "text": "치과 예약 전화", "pinned": False},
        ]
    return json.loads(DATA.read_text(encoding="utf-8"))


def write_memos(memos):
    DATA.write_text(json.dumps(memos, ensure_ascii=False, indent=1), encoding="utf-8")


def export_csv(memos):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "text", "pinned"])
    for m in memos:
        writer.writerow([m["id"], m["text"], m["pinned"]])
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, name):
        data = (STATIC / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/":
            return self.send_file("index.html")
        if path == "/setting":
            return self.send_file("setting.html")
        if path == "/api/memos":
            q = ""
            for part in query.split("&"):
                if part.startswith("q="):
                    from urllib.parse import unquote_plus
                    q = unquote_plus(part[2:])
            memos = [m for m in read_memos() if q in m["text"]]
            memos.sort(key=lambda m: (not m["pinned"], m["id"]))
            return self.send_json(200, memos)
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        memos = read_memos()
        if self.path == "/api/memos":
            text = str(body.get("text", "")).strip()
            if not text:
                return self.send_json(400, {"error": "empty_text"})
            time.sleep(0.8)
            memo = {"id": max([m["id"] for m in memos] or [0]) + 1, "text": text, "pinned": False}
            memos.append(memo)
            write_memos(memos)
            return self.send_json(201, memo)
        if self.path.startswith("/api/memos/") and self.path.endswith("/pin"):
            memo_id = int(self.path.split("/")[3])
            for m in memos:
                if m["id"] == memo_id:
                    m["pinned"] = not m["pinned"]
                    write_memos(memos)
                    return self.send_json(200, m)
            return self.send_json(404, {"error": "not_found"})
        if self.path == "/api/reset":
            if self.headers.get("X-Admin-Token") != os.environ.get("MEMO_ADMIN_TOKEN"):
                return self.send_json(403, {"error": "forbidden"})
            if DATA.exists():
                DATA.unlink()
            return self.send_json(200, {"reset": True})
        self.send_json(404, {"error": "not_found"})

    def do_DELETE(self):
        if self.path.startswith("/api/memos/"):
            memo_id = int(self.path.split("/")[3])
            memos = read_memos()
            kept = [m for m in memos if m["id"] != memo_id or m["pinned"]]
            if len(kept) == len(memos):
                return self.send_json(409, {"error": "pinned_or_missing"})
            write_memos(kept)
            return self.send_json(200, {"deleted": memo_id})
        self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    load_env()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"메모판: http://127.0.0.1:{port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
