"""Check a FEATURE_MAP.md against the code it describes.

Usage: python check_feature_map.py <project-root> [--map FEATURE_MAP.md]

- Every backticked path on a `- 파일:` line must exist under the project root.
  `path::Symbol` also requires Symbol to appear in that file. Line numbers
  (`path:123`) are rejected: they go stale as soon as the code moves.
- Every backticked selector on a `- 선택자:` line must appear, as a distinctive token,
  in at least one source file (html/js/ts/tsx/jsx/vue/svelte/py/css).
  For `#id` the token is `id`; for `.cls` it is `cls`; for `[attr="v"]` it is `v`;
  anything else (widget objectName, menu text) is searched verbatim.
- A bare-word selector (e.g. `CompassStrip`) must appear inside a string literal or a
  text node somewhere; if it only appears as code (a component or function name) it
  cannot be found on screen and is rejected.
- The map must not contain invisible characters (zero-width space etc.), which make
  copied URLs and selectors silently fail.
- Every feature section (`### ...`) must have `파일` and `검증` lines.
Exit code 1 on any problem.
"""
import re
import sys
from pathlib import Path

SOURCE_EXT = {".html", ".htm", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".py", ".css", ".jinja", ".j2", ".ui", ".qml"}
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "__pycache__", "venv", ".venv", ".claude", "worktrees"}
BACKTICK = re.compile(r"`([^`]+)`")
INVISIBLE = re.compile("[​‌‍⁠﻿­]")
BARE_WORD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def in_literal_or_text(tok, corpus):
    """True if tok occurs inside a quoted string or an HTML/JSX text node."""
    return re.search(r"[\"'`>][^\"'`<>\n]*?" + re.escape(tok) + r"[^\"'`<>\n]*?[\"'`<]", corpus) is not None


def source_files(root):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SOURCE_EXT and not (SKIP_DIRS & set(p.relative_to(root).parts)):
            yield p


def selector_token(sel):
    sel = sel.strip()
    m = re.search(r"\[[\w-]+\s*[*^$|~]?=\s*['\"]?([^'\"\]]+)['\"]?\]", sel)
    if m:
        return m.group(1)
    m = re.search(r"#([\w-]+)", sel)
    if m:
        return m.group(1)
    m = re.search(r"\.([A-Za-z_][\w-]*)", sel)
    if m and not re.match(r"^[\w/\\-]+\.\w+$", sel):
        return m.group(1)
    return sel


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(sys.argv[1]).resolve()
    name = sys.argv[sys.argv.index("--map") + 1] if "--map" in sys.argv else "FEATURE_MAP.md"
    fmap = root / name
    if not fmap.exists():
        print(f"FAIL {fmap} not found")
        sys.exit(1)
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in source_files(root))

    problems, features, current, seen = [], 0, None, set()
    for n, line in enumerate(fmap.read_text(encoding="utf-8").splitlines(), 1):
        if INVISIBLE.search(line):
            problems.append(f"line {n}: invisible character U+{ord(INVISIBLE.search(line).group()):04X}")
        if line.startswith("### "):
            if current and not {"파일", "검증"} <= seen:
                problems.append(f"'{current}' is missing {sorted({'파일', '검증'} - seen)}")
            current, seen = line[4:].strip(), set()
            features += 1
            continue
        m = re.match(r"\s*-\s*(파일|선택자|검증|사용자 경로|단축키)\s*:", line)
        if not m or current is None:
            continue
        label = m.group(1)
        seen.add(label)
        if "(미확인)" in line:
            continue
        if label == "파일":
            for entry in BACKTICK.findall(line):
                path, _, symbol = entry.partition("::")
                if re.search(r":\d+", path):
                    problems.append(f"line {n}: `{entry}` has a line number; use `path::Symbol` instead")
                    path = re.sub(r":\d+.*$", "", path)
                target = root / path.split("#")[0]
                if not target.exists():
                    problems.append(f"line {n}: file `{path}` does not exist")
                elif symbol and target.is_file() and symbol not in target.read_text(encoding="utf-8", errors="ignore"):
                    problems.append(f"line {n}: symbol `{symbol}` not found in `{path}`")
        elif label == "선택자":
            for sel in BACKTICK.findall(line):
                tok = selector_token(sel)
                if tok not in corpus:
                    problems.append(f"line {n}: selector `{sel}` (token '{tok}') not found in source")
                elif BARE_WORD.match(sel.strip()) and not in_literal_or_text(tok, corpus):
                    problems.append(f"line {n}: selector `{sel}` only appears as a code identifier, not on screen; move it to 파일 as path::{sel}")
    if current and not {"파일", "검증"} <= seen:
        problems.append(f"'{current}' is missing {sorted({'파일', '검증'} - seen)}")
    if features == 0:
        problems.append("no feature sections (### ...) found")

    for p in problems:
        print(f"FAIL {p}")
    print(f"{features} features, {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
