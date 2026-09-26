"""Tiny stats API. GET /stats?nums=1,2,3 -> {"mean": 2.0}."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


def mean_of(raw):
    nums = [float(x) for x in raw.split(",") if x.strip()]
    return sum(nums) / len(nums)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/stats":
            self.send_response(404)
            self.end_headers()
            return
        raw = parse_qs(url.query, keep_blank_values=True).get("nums", [""])[0]
        body = json.dumps({"mean": mean_of(raw)}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
