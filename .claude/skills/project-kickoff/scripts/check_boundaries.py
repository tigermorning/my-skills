"""Starter for hard guardrails in a new project: fail CI or a pre-commit hook on forbidden patterns.

Usage: python check_boundaries.py [--config guardrails.json] [--root .]

The config lists rules. Each rule must say what to do INSTEAD, because an agent that only
sees "forbidden" takes the next shortcut; one that is told the supported alternative uses it.

  {"rules": [
    {"id": "no-cross-feature-import",
     "paths": ["src/features/**/*.ts"],
     "forbid": "from ['\\"]\\\\.\\\\./\\\\.\\\\./[a-z-]+/",
     "message": "a feature must not import another feature's files",
     "instead": "import from src/shared or call the other feature through its public index.ts"},
    {"id": "no-effect-hook", "paths": ["src/**/*.tsx"], "forbid": "\\\\buseEffect\\\\(",
     "message": "useEffect hides state changes", "instead": "derive the value or use the framework's data hook",
     "except": ["src/shared/legacy/**"]}
  ],
  "comments": {"paths": ["src/**", "scripts/**"], "no_history": true}}

`comments.no_history` rejects comments that record history (a calendar date, who said it, "used
to be"): agents tend to write irrelevant history into comments. Keep the reason, put the history
in the commit message.

Exit code 1 on any violation, printing file:line, the rule, and the alternative.
"""
import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

COMMENT = re.compile(r"(?:^|\s)(?:#|//|/\*|\*|--|<!--)\s*(.*)")
HISTORY = re.compile(r"\b20\d\d-\d\d-\d\d\b|\buser said\b|\bused to\b|\bpreviously\b|\bas requested\b|사용자가 말|이전에는|예전에는|요청으로", re.I)


def tracked_files(root):
    r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if r.returncode == 0 and r.stdout.strip():
        return [Path(root) / p for p in r.stdout.splitlines()]
    return [p for p in Path(root).rglob("*") if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts]


def matches(rel, patterns):
    rel = rel.replace("\\", "/")
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p.replace("**/", "")) for p in patterns)


def check(root, config):
    root = Path(root)
    problems = []
    for rule in config.get("rules", []):
        for key in ("id", "paths", "forbid", "message", "instead"):
            if not rule.get(key):
                problems.append(f"config: rule {rule.get('id', '?')} is missing '{key}' (every rule must say what to do instead)")
    if problems:
        return problems
    files = tracked_files(root)
    text_cache = {}
    for f in files:
        rel = str(f.relative_to(root)).replace("\\", "/")
        rules = [r for r in config.get("rules", []) if matches(rel, r["paths"]) and not matches(rel, r.get("except", []))]
        comment_cfg = config.get("comments", {})
        want_comments = comment_cfg.get("no_history") and matches(rel, comment_cfg.get("paths", ["**"]))
        if not rules and not want_comments:
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        text_cache[rel] = lines
        for n, line in enumerate(lines, 1):
            for r in rules:
                if re.search(r["forbid"], line):
                    problems.append(f"{rel}:{n}: [{r['id']}] {r['message']}. Instead: {r['instead']}")
            if want_comments:
                m = COMMENT.search(line)
                if m and HISTORY.search(m.group(1)):
                    problems.append(f"{rel}:{n}: [comment-history] comment records history; keep the reason and move the history to the commit message")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="guardrails.json")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cfg_path = Path(a.root) / a.config
    if not cfg_path.exists():
        print(f"no {cfg_path}: create it (see the docstring of this script for the format)")
        sys.exit(1)
    problems = check(a.root, json.loads(cfg_path.read_text(encoding="utf-8")))
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
