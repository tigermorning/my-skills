"""Self-test for check_boundaries.py. Run: python test_check_boundaries.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

CONFIG = {
    "rules": [
        {"id": "no-effect", "paths": ["src/**/*.tsx"], "forbid": r"\buseEffect\(", "message": "hides state changes",
         "instead": "derive the value", "except": ["src/legacy/**"]},
    ],
    "comments": {"paths": ["src/**"], "no_history": True},
}


def run(files, config=CONFIG):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "guardrails.json").write_text(json.dumps(config), encoding="utf-8")
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "check_boundaries.py"), "--root", str(root)], capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout


CASES = [
    ("clean file passes", {"src/a.tsx": "const x = 1\n"}, None, 0),
    ("forbidden pattern fails and names the alternative", {"src/a.tsx": "useEffect(() => {})\n"}, None, 1),
    ("except path is allowed", {"src/legacy/a.tsx": "useEffect(() => {})\n"}, None, 0),
    ("other file types are out of scope", {"src/a.ts": "useEffect(() => {})\n"}, None, 0),
    ("history comment fails", {"src/a.tsx": "// fixed on 2026-09-01 per request\nconst x = 1\n"}, None, 1),
    ("python-style history comment fails", {"src/a.py": "# user said never do this\n"}, None, 1),
    ("reason comment passes", {"src/a.tsx": "// keep in sync with the server enum\nconst x = 1\n"}, None, 0),
    ("rule without 'instead' is rejected", {"src/a.tsx": "x\n"}, {"rules": [{"id": "r", "paths": ["src/**"], "forbid": "x", "message": "m"}]}, 1),
]

if __name__ == "__main__":
    failed = 0
    for label, files, cfg, want in CASES:
        code, out = run(files, cfg or CONFIG)
        ok = code == want and (want == 0 or ("Instead:" in out or "instead" in out or "comment-history" in out))
        if not ok:
            failed += 1
            print(f"FAIL {label}: exit {code}, want {want}\n{out}")
    print(f"{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)
