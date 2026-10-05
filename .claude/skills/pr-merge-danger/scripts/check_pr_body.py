"""Check that a PR body (or merge report) carries Summary, Evidence and a Merge Danger call.

Usage:
  python check_pr_body.py BODY.md [--diff CHANGES.diff] [--json]
  python check_pr_body.py --gh 123 [--diff CHANGES.diff] [--json]   # body and diff from `gh pr view/diff`

Exit codes: 0 = body is complete, 1 = something is missing or contradicts the diff, 2 = usage or input error.
The verdict line tells the human how hard to look: one-way door -> full review, two-way -> light review.

Personal one-way signals: a user-level standards file (first found of $REVIEW_STANDARDS,
~/.claude/REVIEW_STANDARDS.md, ~/.claude/references/review-standards.md; --user-standards to name one,
--no-user-standards or REVIEW_STANDARDS="" to skip) may hold a fenced block tagged `one-way`:

  name | repo | where | regex | block
  blog post goes public | tigermorning.github.io | path | ^ko/[^/]+\\.html$ |
  private material leaves its repo | !private-* | content | (?i)secret-project | block

repo is comma-separated globs on the repository folder name (`*` = any, `!glob` = not these);
where is `path` (file paths in diff headers) or `content` (added/removed lines, documents included);
`block` makes a hit fail whatever the Door says.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SECTIONS = {
    "summary": ("summary", "요약"),
    "evidence": ("evidence", "증거", "확인"),
    "merge_danger": ("merge danger", "머지 위험", "합치기 위험"),
}
# "확인 못 한 것" is a different section in Korean reports, so this name must match the whole title.
EXACT_TITLES = {"확인"}
DOOR_WORDS = {"one-way": "one-way", "two-way": "two-way", "단방향": "one-way", "양방향": "two-way"}
# A template slot such as "<one-way | two-way>" counts as unfilled, the same as TODO.
PLACEHOLDER = re.compile(r"^\s*(?:[-*]\s*)?(?:todo|tbd|n/?a|none|없음|추후|나중에|<[^<>]*>)?\s*[.。]?\s*$", re.I)
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
DOC_FILE = re.compile(r"\.(?:md|markdown|txt|rst)$", re.I)

# Changes that are hard to walk back even when the diff is small. A hit while the body says
# two-way is reported, because "simple change" is how irreversible ones slip through.
# Content signals are matched against added/removed code lines only; a context line or a
# sentence in a document is not a change to behaviour.
CONTENT_SIGNALS = [
    (re.compile(r"\b(?:DROP|TRUNCATE|ALTER)\s+(?:TABLE|COLUMN|DATABASE|INDEX|SCHEMA)\b", re.I), "schema change or drop"),
    (re.compile(r"\bDELETE\s+FROM\b", re.I), "bulk delete"),
    # A bare "email" field is everywhere in user models, so only sending calls and mail clients count.
    (re.compile(r"\bsmtp|\bsend_?e?mail\b|\be?mailers?\b|\bmail\s*\(|\bnodemailer\b|\bwebhooks?\b"
                r"|\bpush_?notification", re.I), "outbound message"),
    (re.compile(r"\bgit\s+push\b|\bforce[- ]push\b|\bnpm\s+publish\b|\btwine\s+upload\b|\bdocker\s+push\b"
                r"|\bgh\s+release\s+create\b", re.I), "publish or push"),
    (re.compile(r"\bterraform\s+apply\b|\bkubectl\s+apply\b", re.I), "deploy or infrastructure change"),
    (re.compile(r"\brm\s+-[a-z]*r[a-z]*\b|['\"]rm['\"]\s*,\s*['\"]-[a-z]*r[a-z]*['\"]|\bshutil\.rmtree\b"
                r"|\bos\.(?:remove|unlink)\b|\bunlink\(|\brmSync\b", re.I), "file deletion"),
]
# Path signals are matched against the file paths named in diff headers only.
PATH_SIGNALS = [
    (re.compile(r"(?:^|/)(?:migrations?|db/migrate|alembic/versions)/", re.I), "database migration"),
    (re.compile(r"(?:^|/)\.github/workflows/|(?:^|/)\.gitlab-ci\.ya?ml$|(?:^|/)deploy(?:ment)?(?:/|\.[^/]+$)", re.I),
     "deploy or CI pipeline"),
    # Example env files hold no secret and are meant to be committed.
    (re.compile(r"(?:^|/)\.env(?:\.(?!example$|sample$|template$)[\w.-]+)?$", re.I), "secrets or credentials"),
    (re.compile(r"(?:^|/)openapi[\w.-]*\.(?:ya?ml|json)$|\.proto$|(?:^|/)schemas?[\w.-]*\.\w+$", re.I),
     "public contract (API, schema, wire format)"),
]


class InputError(Exception):
    pass


USER_STANDARDS = ("~/.claude/REVIEW_STANDARDS.md", "~/.claude/references/review-standards.md")


def find_user_standards(explicit=None, skip=False):
    """Path of the user-level standards file, or None. An explicit path that is missing is an
    error, because a rule the user wrote and believes is running must not vanish silently."""
    if skip:
        return None
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise InputError(f"user standards file not found: {explicit}")
        return p
    env = os.environ.get("REVIEW_STANDARDS")
    if env is not None:
        if not env.strip():
            return None
        return find_user_standards(env)
    for c in USER_STANDARDS:
        p = Path(c).expanduser()
        if p.is_file():
            return p
    return None


def load_user_signals(path):
    """Rules from the ```one-way block of the user standards file."""
    rules, in_block = [], False
    for n, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not in_block:
            in_block = bool(re.match(r"^(`{3,}|~{3,})\s*one-way\s*$", line))
            continue
        if FENCE.match(line):
            break
        if not line or line.startswith("#"):
            continue
        # A cell boundary is a pipe with a space before it and a space or the line end after it, so an
        # empty last cell ("regex |") does not glue " |" onto the regex as an always-true alternative.
        cells = [c.strip() for c in re.split(r"\s\|(?=\s|$)", line)]
        if len(cells) < 4 or cells[2] not in ("path", "content"):
            raise InputError(f"{path}:{n}: one-way rule needs 'name | repo | path|content | regex [| block]'")
        try:
            pattern = re.compile(cells[3])
        except re.error as e:
            raise InputError(f"{path}:{n}: bad regex {cells[3]!r}: {e}")
        if pattern.search(""):
            raise InputError(f"{path}:{n}: regex {cells[3]!r} matches the empty string, so it would flag every change")
        rules.append({"label": cells[0], "repo": cells[1] or "*", "where": cells[2], "pattern": pattern,
                      "block": len(cells) > 4 and cells[4].lower() in ("block", "막기")})
    return rules


def repo_matches(spec, repo):
    """spec: comma-separated globs; `!glob` excludes, plain globs (if any) must match one, `*` is any repo.
    A rule scoped by name never runs when the repo name is unknown."""
    globs = [g.strip() for g in spec.split(",") if g.strip()] or ["*"]
    pos = [g for g in globs if not g.startswith("!")]
    neg = [g[1:] for g in globs if g.startswith("!")]
    if repo is None:
        return pos == ["*"] and not neg
    name = repo.lower()
    if any(fnmatch.fnmatch(name, g.lower()) for g in neg):
        return False
    return not pos or any(g == "*" or fnmatch.fnmatch(name, g.lower()) for g in pos)


def current_repo():
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None
    return Path(r.stdout.strip()).name if r.returncode == 0 and r.stdout.strip() else None


def section_key(title):
    title = title.strip().rstrip(":：").strip().lower()
    for key, names in SECTIONS.items():
        for n in names:
            if title == n or (n not in EXACT_TITLES and title.startswith(n)):
                return key
    return None


def split_sections(body):
    """Section text keyed by name. A section ends at the next heading of the same or higher level,
    so sub-headings (### Call tree) stay inside it; lines in code fences are never headings."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    found, current, depth, fence = {}, None, 0, None
    for line in body.splitlines():
        f = FENCE.match(line)
        if fence:
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= len(fence):
                fence = None
            if current:
                found[current].append(line)
            continue
        if f:
            fence = f.group(1)
            if current:
                found[current].append(line)
            continue
        m = HEADING.match(line)
        if m:
            level, key = len(m.group(1)), section_key(m.group(2))
            if key:
                current, depth = key, level
                found.setdefault(key, [])
                continue
            if current and level <= depth:
                current = None
        if current:
            found[current].append(line)
    return {k: "\n".join(v).strip() for k, v in found.items()}


def is_empty(text):
    lines = [ln for ln in text.splitlines() if ln.strip() and not HEADING.match(ln) and not FENCE.match(ln)]
    return all(PLACEHOLDER.match(ln) for ln in lines)


def plain(value):
    return re.sub(r"[*`]", "", value).strip().strip("_").strip()


def field(text, *names):
    """Value of 'Name: value', or of a '### Name' sub-heading followed by the value on the next line."""
    lines = text.splitlines()
    for name in names:
        esc = re.escape(name)
        for i, line in enumerate(lines):
            m = re.match(rf"^\s*(?:[-*]\s*)?[*_]*{esc}[*_]*\s*[:：]\s*(.*?)\s*$", line, re.I)
            if m:
                return plain(m.group(1))
            h = HEADING.match(line)
            if h and h.group(2).strip().rstrip(":：").strip().lower() == name:
                for nxt in lines[i + 1:]:
                    if nxt.strip():
                        return "" if HEADING.match(nxt) else plain(nxt)
    return ""


def read_door(raw):
    """(door, problem). The words in parentheses are the reason, not the value."""
    if not raw:
        return None, "Merge Danger needs 'Door: one-way' or 'Door: two-way'"
    if PLACEHOLDER.match(raw):
        return None, f"Door is still a template slot ('{raw}'); write one-way or two-way"
    main = re.sub(r"\([^)]*\)|（[^）]*）", " ", raw.lower())
    main = re.sub(r"\b(one|two)[\s_]+way\b", r"\1-way", main)
    values = {v for w, v in DOOR_WORDS.items() if w in main}
    if len(values) == 2:
        return None, f"Door names both one-way and two-way ('{raw}'); pick one"
    if not values:
        return None, f"Door must be one-way or two-way, got '{raw}'"
    return values.pop(), None


def reason_of(danger, door_raw):
    r = field(danger, "reason", "이유")
    if r and not PLACEHOLDER.match(r):
        return r
    m = re.search(r"\(([^)]*)\)|（([^）]*)）", door_raw or "")
    inner = (m.group(1) or m.group(2) or "").strip() if m else ""
    return inner if inner and not PLACEHOLDER.match(inner) else ""


def diff_paths(header):
    if header.startswith("diff --git "):
        return re.findall(r"(?:^| )[ab]/(\S+)", header[len("diff --git"):])
    p = header[4:].split("\t")[0].strip()
    if p == "/dev/null":
        return []
    return [re.sub(r"^[ab]/", "", p)]


def scan_diff(diff, user_rules=(), repo=None):
    return scan_signals(diff, user_rules, repo)[0]


def scan_signals(diff, user_rules, repo):
    """(one-way signal labels, user rules that matched): path signals from header lines, content signals from +/- lines of
    non-document files. '---'/'+++' inside a hunk is a changed line, not a header.
    User rules (already filtered by repo) also read documents: a private name in a README leaks too."""
    hits, in_hunk, doc = [], False, False
    mine = [r for r in user_rules if repo_matches(r["repo"], repo)]
    user_hits = []

    def add(label):
        if label not in hits:
            hits.append(label)

    def add_user(rule):
        if rule["label"] not in [u["label"] for u in user_hits]:
            user_hits.append(rule)
            add(f"yours: {rule['label']}")

    lines = diff.splitlines()
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        prev = lines[i - 1] if i else ""
        # A plain `diff -u` of several files has no "diff --git" line; a ---/+++ pair still marks a header.
        pair = (line.startswith("--- ") and nxt.startswith("+++ ")) or (line.startswith("+++ ") and prev.startswith("--- "))
        header = line.startswith("diff --git ") or pair or (not in_hunk and re.match(r"^(?:\+\+\+|---) \S", line))
        if header:
            in_hunk = False
            paths = diff_paths(line)
            if paths:
                doc = all(DOC_FILE.search(p) for p in paths)
            for p in paths:
                for rule in mine:
                    if rule["where"] == "path" and rule["pattern"].search(p):
                        add_user(rule)
                if DOC_FILE.search(p):
                    continue
                for pattern, label in PATH_SIGNALS:
                    if pattern.search(p):
                        add(label)
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if line[:1] in ("+", "-"):
            for rule in mine:
                if rule["where"] == "content" and rule["pattern"].search(line[1:]):
                    add_user(rule)
            if doc:
                continue
            for pattern, label in CONTENT_SIGNALS:
                if pattern.search(line[1:]):
                    add(label)
    return hits, user_hits


def check(body, diff=None, user_rules=(), repo=None):
    problems, warnings = [], []
    sections = split_sections(body.lstrip("﻿"))
    for key in SECTIONS:
        if key not in sections:
            problems.append(f"missing section: {SECTIONS[key][0].title()} (heading '## {SECTIONS[key][0].title()}')")
        elif is_empty(sections[key]):
            problems.append(f"section is empty or a placeholder: {SECTIONS[key][0].title()}")

    danger = sections.get("merge_danger", "")
    door_raw = field(danger, "door", "문")
    door, radius = None, field(danger, "blast radius", "영향 범위")
    if "merge_danger" in sections:
        door, door_problem = read_door(door_raw)
        if door_problem:
            problems.append(door_problem)
        if not radius or PLACEHOLDER.match(radius):
            problems.append("Merge Danger needs 'Blast radius: <one word>', e.g. localized, module, users, data")
            radius = ""

    hits, user_hits = scan_signals(diff, user_rules, repo) if diff else ([], [])
    for rule in user_hits:
        if rule["block"]:
            problems.append(f"blocked by your one-way rule: {rule['label']} — take it out of this change")
    if hits and door == "two-way":
        warnings.append("diff has one-way signals (" + ", ".join(hits) + "); say why it is still two-way or mark it one-way")
        if not reason_of(danger, door_raw):
            problems.append("two-way door claimed next to one-way signals without a reason: "
                            "add 'Reason: ...' or put it in parentheses on the Door line")

    review = {"one-way": "full", "two-way": "light"}.get(door, "unknown")
    return {"ok": not problems, "door": door, "blast_radius": radius or None, "review": review,
            "one_way_signals": hits, "problems": problems, "warnings": warnings}


def read_text_file(path, what):
    try:
        data = Path(path).expanduser().read_bytes()
    except OSError as e:
        raise InputError(f"cannot read {what} '{path}': {e}")
    # PowerShell's `git diff > f` writes UTF-16; decoding that as UTF-8 would silently find nothing.
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in data:
        raise InputError(f"{what} '{path}' looks like UTF-16 or binary; save it as UTF-8 "
                         "(e.g. git diff --output=changes.diff)")
    return data.decode("utf-8-sig", errors="replace")


def gh(args):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    except OSError as e:
        raise InputError(f"cannot run gh: {e}")
    if r.returncode != 0:
        raise InputError(f"gh {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("body", nargs="?", help="markdown file with the PR body")
    ap.add_argument("--gh", metavar="PR", help="read the body and diff of this PR with the gh CLI")
    ap.add_argument("--diff", help="diff file to scan for one-way signals")
    ap.add_argument("--user-standards", metavar="FILE", help="user-level standards file with a ```one-way block")
    ap.add_argument("--no-user-standards", action="store_true", help="ignore the user-level standards file")
    ap.add_argument("--repo", help="repository folder name for repo-scoped rules (default: this git checkout)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    # Korean text must survive a Windows console whose default codec is cp949.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if bool(a.body) == bool(a.gh):
        print("give either a body file or --gh PR, not both", file=sys.stderr)
        ap.print_usage(sys.stderr)
        return 2
    try:
        if a.gh:
            body = gh(["pr", "view", a.gh, "--json", "body", "-q", ".body"])
            diff = read_text_file(a.diff, "diff") if a.diff else gh(["pr", "diff", a.gh])
        else:
            body = read_text_file(a.body, "body")
            diff = read_text_file(a.diff, "diff") if a.diff else None
        std = find_user_standards(a.user_standards, a.no_user_standards)
        rules = load_user_signals(std) if std else []
    except InputError as e:
        print(e, file=sys.stderr)
        return 2

    repo = a.repo or current_repo()
    rep = check(body, diff, rules, repo)
    rep["user_standards"] = str(std) if std else None
    rep["repo"] = repo
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(f"door={rep['door']} blast_radius={rep['blast_radius']} review={rep['review']}"
              f" user_rules={len(rules)}{' from ' + rep['user_standards'] if std else ''}")
        for p in rep["problems"]:
            print(f"FAIL {p}")
        for w in rep["warnings"]:
            print(f"WARN {w}")
        if rep["problems"]:
            print("Fix: add '## Summary', '## Evidence' and '## Merge Danger' with 'Door:' and 'Blast radius:' lines.")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
