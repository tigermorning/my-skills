"""Record that a skill's evals were run against its current SKILL.md.

Usage:
    python record_run.py <skill-name> --model <model> --passed N --total M [--note "..."]

Writes .claude/skills/<skill>/evals/last_run.json with the SKILL.md hash, so
check_skills.py can tell when a skill was edited without rerunning its evals.
Only run this after the evals actually ran on the current SKILL.md.
"""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent.parent / ".claude" / "skills"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("skill")
    ap.add_argument("--model", required=True)
    ap.add_argument("--passed", type=int, required=True)
    ap.add_argument("--total", type=int, required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    skill_md = SKILLS / a.skill / "SKILL.md"
    record = {
        "skill_sha256": hashlib.sha256(skill_md.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "date": date.today().isoformat(),
        "model": a.model,
        "passed": a.passed,
        "total": a.total,
        "note": a.note,
    }
    out = SKILLS / a.skill / "evals" / "last_run.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {a.skill}: {a.passed}/{a.total} on {a.model}")
