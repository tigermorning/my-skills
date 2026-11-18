"""Append one line to ~/.claude/logs/gates.jsonl when a guard fires.

Same format as the node gates (ts, gate, result, detail) so one weekly count covers all.
Logging must never break the guard, so every error is swallowed.
"""
import json
import os
from datetime import datetime, timezone


def log(gate, result, detail=""):
    try:
        d = os.path.join(os.path.expanduser("~"), ".claude", "logs")
        os.makedirs(d, exist_ok=True)
        line = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "gate": gate,
            "result": result,
            "detail": str(detail)[:200],
        }
        with open(os.path.join(d, "gates.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass
