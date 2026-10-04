"""Collect human feedback given to agents and point out remarks that were made more than once.

Sources (use one or both):
  --gh-repo OWNER/REPO --days 7     review comments, reviews and PR comments on PRs merged in the window (needs gh)
  --transcripts PATH [PATH ...]     Claude Code transcripts (*.jsonl) or folders of them; keeps what the human typed.
                                    Each folder counts as one project, so a repeat is marked "shared by N projects"
                                    (user-level standards) or "project X" (that repository's standards)
  --exclude-author LOGIN            skip this GitHub author (repeatable); bots are skipped already

Output: markdown (default) or --json, with every remark, a "repeated" list of remarks that look alike
across different PRs or sessions, and a "repeated within one source" list (the same thing said again in
one session or PR). Similarity is word overlap, so it is a shortlist for a person or an agent to judge,
not a verdict.
"""
import argparse
import datetime as dt
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

MIN_WORDS = 3
SIMILAR = 0.5
GH_LIMIT = 200
# Approvals and chatter repeat by nature; flagging them as "same remark twice" is noise.
TRIVIAL = re.compile(r"^\s*(?:lgtm|looks good|thanks?|ok(?:ay)?|좋아요|좋습니다|감사합니다|네|응|ㅇㅋ|이어서|계속)[.!]*\s*$", re.I)
# Zero remarks is ambiguous (quiet reviews or a broken reader), so the report always says how much was read.
SCANNED = {"prs": 0, "sessions": 0}
WARNINGS = []
# Without an origin field, a block that opens with a markup tag was injected by the harness or a scheduler.
SYSTEMISH = re.compile(r"^\s*(?:<[a-z][\w-]*[\s>]|\[Request interrupted)", re.I)
# A human message can carry injected blocks wrapped whole in one tag (system reminders); the human's own
# text may still start with a tag such as <b>, so only fully wrapped blocks are dropped.
WRAPPED = re.compile(r"^\s*<([a-z][\w-]*)[^>]*>.*</\1>\s*$", re.S | re.I)
INTERRUPTED = re.compile(r"^\s*\[Request interrupted[^\]]*\]\s*")


def words(text):
    return {w for w in re.findall(r"[0-9A-Za-z가-힣_]{2,}", text.lower())}


def keep(text):
    t = text.strip()
    return bool(t) and not TRIVIAL.match(t) and len(words(t)) >= MIN_WORDS


def find_groups(remarks):
    """Union-find over pairs with word Jaccard >= SIMILAR.

    Prefix filtering keeps this near-linear: with words ordered rarest first, two sets that reach the
    threshold must share a word within each one's first len - ceil(SIMILAR * len) + 1 words, so only
    pairs sharing such a word are compared.
    """
    sets = [words(r["text"]) for r in remarks]
    freq = Counter(w for s in sets for w in s)
    parent = list(range(len(remarks)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    index = defaultdict(list)
    for i, s in enumerate(sets):
        if not s:
            continue
        prefix = sorted(s, key=lambda w: (freq[w], w))[: len(s) - math.ceil(SIMILAR * len(s)) + 1]
        candidates = {j for w in prefix for j in index[w]}
        for j in candidates:
            inter = len(s & sets[j])
            if inter / (len(s) + len(sets[j]) - inter) >= SIMILAR:
                parent[root(i)] = root(j)
        for w in prefix:
            index[w].append(i)
    groups = {}
    for i in range(len(remarks)):
        groups.setdefault(root(i), []).append(remarks[i])
    return [g for g in groups.values() if len(g) >= 2]


def find_repeats(remarks):
    """(across, within): alike groups spanning two or more sources, and groups inside one source."""
    across, within = [], []
    for members in find_groups(remarks):
        sources = sorted({m["source"] for m in members})
        # The same lesson in two projects belongs in user-level standards; in one project, in that repo.
        projects = sorted({m["project"] for m in members if m.get("project")})
        g = {"count": len(members), "sources": sources, "members": members, "projects": projects,
             "scope": "shared" if len(projects) >= 2 else "project"}
        (across if len(sources) >= 2 else within).append(g)
    across.sort(key=lambda g: (-len(g["sources"]), -g["count"]))
    within.sort(key=lambda g: -g["count"])
    return across, within


def gh_json(args):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"cannot run gh: {e}")
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def is_bot(author):
    author = author or {}
    login = author.get("login") or ""
    return author.get("type") == "Bot" or bool(author.get("is_bot") or author.get("isBot")) or login.endswith("[bot]")


def from_github(repo, since, excluded=(), gh=gh_json):
    prs = gh(["pr", "list", "--repo", repo, "--state", "merged", "--limit", str(GH_LIMIT),
              "--search", f"merged:>={since.isoformat()}", "--json", "number,title,url"]) or []
    if len(prs) >= GH_LIMIT:
        WARNINGS.append(f"gh returned {GH_LIMIT} PRs, the limit; older PRs in the window were not read. Use fewer --days.")
    out = []
    for pr in prs:
        SCANNED["prs"] += 1
        src = f"PR #{pr['number']} {pr['title']}"
        view = gh(["pr", "view", str(pr["number"]), "--repo", repo, "--json", "comments,reviews"]) or {}
        inline = gh(["api", f"repos/{repo}/pulls/{pr['number']}/comments", "--paginate"]) or []
        items = [(c.get("author"), c.get("body", "")) for c in view.get("comments") or []]
        items += [(r.get("author"), r.get("body", "")) for r in view.get("reviews") or []]
        items += [(c.get("user"), c.get("body", "")) for c in inline]
        for author, body in items:
            login = (author or {}).get("login")
            if is_bot(author) or login in excluded:
                continue
            if keep(body or ""):
                out.append({"source": src, "where": pr["url"], "who": login, "text": body.strip(),
                            "project": repo.split("/")[-1]})
    return out


def human_text(ev):
    """What the human typed in this event, or '' when it is not theirs."""
    content = (ev.get("message") or {}).get("content")
    if isinstance(content, str):
        blocks = [content]
    elif isinstance(content, list):
        blocks = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    else:
        return ""
    origin = ev.get("origin")
    if isinstance(origin, dict) and origin.get("kind"):
        if origin["kind"] != "human":
            return ""
        blocks = [INTERRUPTED.sub("", b) for b in blocks if not WRAPPED.match(b)]
    else:
        blocks = [b for b in blocks if not SYSTEMISH.match(b)]
    return "\n".join(b.strip() for b in blocks if b.strip())


def from_transcripts(path, since, seen=None):
    path = Path(path).expanduser()
    files = [path] if path.is_file() else sorted(path.glob("*.jsonl"))
    # Claude Code keeps a worktree's sessions in "<project>--claude-worktrees-<name>"; that is still one project,
    # and counting it separately would mark a single project's habit as shared across projects.
    project = re.sub(r"--claude-worktrees-.+$", "", path.parent.name if path.is_file() else path.name)
    out = []
    # Resumed or forked sessions copy earlier messages with their uuid; counting those would
    # report every resumed session as the human repeating themselves.
    seen = set() if seen is None else seen
    for f in files:
        # A file untouched since the window opened holds no message inside it; the window itself is
        # checked per message below because a long-lived session file keeps old messages.
        if dt.date.fromtimestamp(f.stat().st_mtime) < since:
            continue
        SCANNED["sessions"] += 1
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict) or ev.get("type") != "user" or ev.get("isMeta") or ev.get("isCompactSummary"):
                continue
            stamp = str(ev.get("timestamp", ""))[:10]
            if stamp and stamp < since.isoformat():
                continue
            if ev.get("uuid"):
                if ev["uuid"] in seen:
                    continue
                seen.add(ev["uuid"])
            text = human_text(ev)
            if keep(text):
                out.append({"source": f.name, "where": f"{f.name}:{n}", "who": "human", "text": text, "project": project})
    return out


def short(text, n=160):
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def group_lines(groups):
    lines = []
    if not groups:
        lines.append("- none found")
    for g in groups:
        where = (f"shared by {len(g['projects'])} projects" if g.get("scope") == "shared"
                 else f"project {g['projects'][0]}" if g.get("projects") else "project unknown")
        lines.append(f"- {g['count']} times in {len(g['sources'])} source(s) [{where}]: {short(g['members'][0]['text'])}")
        for m in g["members"][1:4]:
            lines.append(f"  - `{m['where']}`: {short(m['text'], 100)}")
        if g["count"] > 4:
            lines.append(f"  - … {g['count'] - 4} more")
    return lines


def markdown(remarks, across, within):
    lines = [f"# Feedback collected: {len(remarks)} remarks, {len(across)} possible repeats across sources, "
             f"{len(within)} within one source", "",
             f"Scanned: {SCANNED['prs']} merged PRs, {SCANNED['sessions']} sessions", ""]
    lines += [f"> WARNING: {w}" for w in WARNINGS]
    lines += ["## Possible repeats across sources (judge each: same lesson or coincidence?)", ""]
    lines += group_lines(across)
    lines += ["", "## Said again in the same session or PR", ""]
    lines += group_lines(within)
    lines += ["", "## All remarks", ""]
    for r in remarks:
        lines.append(f"- `{r['where']}` ({r['who']}): {short(r['text'])}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gh-repo")
    ap.add_argument("--transcripts", nargs="+", metavar="PATH", help="one or more transcript files or folders")
    ap.add_argument("--exclude-author", action="append", default=[])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    # Korean text must survive a Windows console whose default codec is cp949.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if not a.gh_repo and not a.transcripts:
        ap.print_usage(sys.stderr)
        return 2
    since = dt.date.today() - dt.timedelta(days=a.days)
    remarks = []
    missing = [t for t in a.transcripts or [] if not Path(t).expanduser().exists()]
    if missing:
        print(f"no such file or directory: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        if a.gh_repo:
            remarks += from_github(a.gh_repo, since, set(a.exclude_author))
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2
    seen = set()
    for t in a.transcripts or []:
        remarks += from_transcripts(t, since, seen)
    for w in WARNINGS:
        print(f"WARNING: {w}", file=sys.stderr)
    across, within = find_repeats(remarks)
    if a.json:
        print(json.dumps({"scanned": SCANNED, "warnings": WARNINGS, "remarks": remarks, "repeats": across,
                          "repeats_within_source": within}, ensure_ascii=False, indent=2))
    else:
        print(markdown(remarks, across, within))
    return 0


if __name__ == "__main__":
    sys.exit(main())
