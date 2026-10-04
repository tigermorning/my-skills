"""Scope check: did a worker branch stay inside the files its task card lists, and did it say so when not?

Verdicts per changed file:
  OK    inside the card's list
  WARN  outside the list but the worker named it in the report (a person reads it before merging)
  FAIL  outside the list and not named in the report, or a report section is missing

"Outside" has two weights. A file the card simply does not list counts as named when the report
mentions it anywhere. A file the card forbids, or a file outside the project folder, must appear
in one of the report's strict sections - a passing mention elsewhere does not count. Changing a
judge file (this kit, the quick check) is always WARN.

The card is read as it was on the target branch (or from card.ref), never from the worker's tree,
so a worker cannot widen its own card.

Usage (from anywhere inside the repo):
  python scope_check.py --branch worker/T-012            judge that branch as if merged into HEAD
  python scope_check.py --tip <rev> --into <rev> --card T-012
  python scope_check.py --worktree [--soft]              inside a worker worktree, uncommitted files too
  python scope_check.py --retro [--limit 50]             replay every past worker merge on the guarded branch
Options: --config PATH (default <repo>/.merge-gate/config.json) · --repo DIR · --soft (always exit 0)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULTS = {
    "guarded_branch": "main",
    "project_dir": ".",
    "worker_branch": r"^worker/(T-\d+[a-z]?)",
    "card_id": r"T-\d+[a-z]?",
    "card": {"path": "docs/tasks/{id}.md", "ref": None, "strip": [],
             "section": r"^(만지는 파일|Files)", "ban": r"^(고치지 않음|Do not touch)"},
    "aliases": {},
    "report": {
        "path": "docs/reports/{id}.md",
        "sections": [r"^(한 것|Done)", r"^(확인|Checks)", r"^(막힌 것|Blocked)", r"^(합칠 때 주의|Merge notes)"],
        "strict": [r"^(합칠 때 주의|Merge notes)", r"^(막힌 것|Blocked)"],
        "numbers_in": r"^(확인|Checks)",
    },
    "judges": [".merge-gate/"],
}

# A hook exports the variables that locate the repo; a child git would then look in the wrong place.
REPO_VARS = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR", "GIT_NAMESPACE",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_QUARANTINE_PATH"}
CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in REPO_VARS}
FENCE = re.compile(r"^\s*(```|~~~)")
BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=repo, env=CLEAN_ENV,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULTS))
    if path and Path(path).exists():
        user = json.loads(Path(path).read_text(encoding="utf-8"))
        for k, v in user.items():
            cfg[k] = {**cfg[k], **v} if isinstance(cfg.get(k), dict) and isinstance(v, dict) and k != "aliases" else v
    return cfg


# ---------- markdown: lines inside code fences are never headings or bullets
def outside_fence(lines):
    fence, out = None, []
    for line in lines:
        m = FENCE.match(line)
        if m and (fence is None or m.group(1) == fence):
            fence = None if fence else m.group(1)
            out.append(False)
        else:
            out.append(fence is None)
    return out


def heading(line):
    m = re.match(r"^(#{1,6})\s+(.*)", line)
    return (len(m.group(1)), m.group(2).replace("*", "").strip()) if m else (0, None)


def section(text, head_re):
    """Body under the first heading matching head_re, up to the next heading of the same or higher level."""
    lines = text.splitlines()
    ok = outside_fence(lines)
    heads = [(i, *heading(l)) for i, l in enumerate(lines) if ok[i] and heading(l)[1] is not None]
    start = next(((i, d) for i, d, t in heads if re.search(head_re, t)), None)
    if start is None:
        return None
    end = next((i for i, d, _ in heads if i > start[0] and d <= start[1]), len(lines))
    return "\n".join(lines[start[0] + 1:end])


def bullet(text, head_re):
    """A top-level bullet whose text starts with the section name, plus the indented lines under it."""
    lines = text.splitlines()
    ok = outside_fence(lines)
    for i, line in enumerate(lines):
        m = re.match(r"^- (.*)", line)
        if ok[i] and m and re.search(head_re, m.group(1).replace("*", "")):
            j = i + 1
            while j < len(lines) and (re.match(r"^\s+\S", lines[j]) or not lines[j].strip()):
                j += 1
            return "\n".join([re.sub(r"^- [^:]*:", "", line), *lines[i + 1:j]])
    return None


def part(text, head_re):
    found = [s for s in (section(text, head_re), bullet(text, head_re)) if s is not None]
    return "\n".join(found) if found else None


def heads_of(text):
    """Section names: every heading, plus top-level bullets used as fields ("- Done: …", or any top-level
    bullet before the first ##-level heading). A bullet inside a section body is content, not a field."""
    lines = text.splitlines()
    ok = outside_fence(lines)
    first_sub = next((i for i, l in enumerate(lines) if ok[i] and heading(l)[0] >= 2), len(lines))
    out = []
    for i, line in enumerate(lines):
        if not ok[i]:
            continue
        _, title = heading(line)
        if title is not None:
            out.append(title)
        elif line.startswith("- ") and (i < first_sub or re.match(r"^- [^:\n]{1,40}:", line)):
            out.append(line[2:62].replace("*", "").strip())
    return out


def mentions(text, name):
    """name appears as a whole path or file name, not as part of a longer one."""
    return re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-]|\.\w)", text) is not None


# ---------- card
def pathish(t):
    return bool(re.fullmatch(r"[\w.\-*/@+]+", t)) and any(c in t for c in "./*")


def expand(token, strip_prefixes):
    t = token.strip()
    for prefix in strip_prefixes:  # cards may write paths from the repo root or from a tool root
        if prefix and t.startswith(prefix):
            t = t[len(prefix):]
            break
    opt = re.fullmatch(r"(.*)\((\.[\w.]+)\)", t)  # `a.glb(.mjs)` means both a.glb and a.glb.mjs
    return [p for p in ([opt.group(1), opt.group(1) + opt.group(2)] if opt else [t]) if pathish(p)]


def parse_card(text, cfg, strip_prefix):
    body = section(text, cfg["card"]["section"])
    if body is None:
        return None
    strips = [strip_prefix, *cfg["card"].get("strip", [])]
    allow, ban, alias_ban, unread = [], [], [], []
    heading_mode = mode = "allow"
    for raw in body.splitlines():
        _, title = heading(raw)
        if title is not None:  # a sub-heading such as "### Do not touch" switches what follows
            heading_mode = mode = "ban" if re.search(cfg["card"]["ban"], title) else "allow"
            continue
        m = BULLET.match(raw)
        if not m:
            continue
        text_ = m.group(2).replace("**", "")
        ban_here = bool(re.search(cfg["card"]["ban"], text_))
        if not m.group(1):
            mode = "ban" if ban_here else heading_mode  # an indented bullet belongs to the bullet above it
        is_ban = ban_here or mode == "ban"
        for tok in re.findall(r"`([^`]+)`", m.group(2)):
            paths = expand(tok, strips)
            (ban if is_ban else allow).extend(paths)
            if is_ban and not paths:
                unread.append(f"`{tok}`")  # a forbidden path the parser cannot read must not vanish silently
        if not is_ban:
            continue
        rest = re.sub(cfg["card"]["ban"], "", text_)
        rest = re.sub(r"`[^`]*`", "", re.sub(r"\([^)]*\)", "", rest))
        for w in (re.sub(r"[:：\s]+", " ", w).strip() for w in re.split(r"[,·.]", rest)):
            if not w:
                continue
            key = next((k for k in cfg["aliases"] if w == k or w.startswith(k)), None)
            if key:
                alias_ban.extend((p, key) for p in cfg["aliases"][key])
            else:
                unread.append(w)
    return allow, ban, alias_ban, unread


def hit(pattern, rel):
    if pattern.endswith("/"):
        return rel.startswith(pattern)
    target = rel if "/" in pattern else rel.rsplit("/", 1)[-1]  # a bare name matches the file anywhere
    rx = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(rx, target) is not None


def read_card(top, cfg, card_id, into, cards_dir):
    """Card text as the target branch has it; the working file only when git has no copy."""
    notes = []
    if cards_dir:
        p = Path(cards_dir) / f"{card_id}.md"
        return (p.read_text(encoding="utf-8") if p.exists() else None), str(p), notes
    rel = cfg["card"]["path"].format(id=card_id)
    absolute = Path(os.path.expanduser(rel)).is_absolute()
    if cfg["card"].get("ref"):
        where = cfg["card"]["ref"].format(id=card_id)
        text = git(top, "show", where, check=False)
    elif not absolute:
        where = f"{into}:{rel}"
        text = git(top, "show", where, check=False)
    else:
        where, text = rel, None
    work_path = Path(os.path.expanduser(rel)) if absolute else Path(top) / rel
    work = work_path.read_text(encoding="utf-8") if work_path.exists() else None
    if text is None:
        if work is not None and not absolute:
            notes.append(f"카드가 {where} 에 없음 — 작업 파일로 판정(일꾼이 고칠 수 있는 판)")
        return work, str(work_path), notes
    if work is not None and work.replace("\r\n", "\n").strip() != text.replace("\r\n", "\n").strip():
        notes.append(f"카드 작업 파일이 {where} 와 다름 — {where} 로 판정")
    return text, where, notes


# ---------- one judgement
def judge(repo, cfg, card_id, tip=None, into="HEAD", worktree=False, cards_dir=None):
    """Return (lines, n_fail, summary). tip None + worktree True means the working tree of repo."""
    top = git(repo, "rev-parse", "--show-toplevel")
    project = cfg["project_dir"].strip("/")
    project = "" if project in ("", ".") else project + "/"
    base = git(top, "merge-base", into, tip or "HEAD", check=False)
    if not base:
        return [f"✘ {into} 와 {tip or 'HEAD'} 의 공통 조상을 못 찾음"], 1, "판정 못 함"
    if worktree:
        changed = sorted(set(filter(None, (git(top, "diff", "--no-renames", "--name-only", base) or "").splitlines()))
                         | set(filter(None, (git(top, "ls-files", "--others", "--exclude-standard") or "").splitlines())))
    else:
        changed = list(filter(None, (git(top, "diff", "--no-renames", "--name-only", base, tip) or "").splitlines()))

    card, where, notes = read_card(top, cfg, card_id, into, cards_dir)
    if card is None:
        return [f"✘ 카드 {card_id} 를 못 찾음({where})"], 1, "판정 못 함"
    parsed = parse_card(card, cfg, project)
    if parsed is None:
        return [f"✘ 카드 {card_id} 에 만지는 파일 칸이 없음({cfg['card']['section']})"], 1, "판정 못 함"
    allow, ban, alias_ban, unread = parsed

    rep_path = cfg["report"]["path"].format(id=card_id)
    if worktree:
        rp = Path(top) / rep_path
        report = rp.read_text(encoding="utf-8") if rp.exists() else None
    else:
        report = git(top, "show", f"{tip}:{rep_path}", check=False)
    ticks = [t[len(project):] if project and t.startswith(project) else t for t in re.findall(r"`([^`\s]+)`", report or "")]
    near = "\n".join(filter(None, (part(report, h) for h in cfg["report"]["strict"]))) if report else ""
    near_ticks = re.findall(r"`([^`\s]+)`", near)

    def stem(p):
        return p.rsplit("/", 1)[-1].split(".", 1)[0]

    def loose(f, rel):
        name = f.rsplit("/", 1)[-1]
        if not report:
            return False
        if mentions(report, name) or mentions(report, rel):
            return True
        if any(t == name.rsplit(".", 1)[0] or ("*" in t and hit(t, rel)) for t in ticks):
            return True
        folder = f.rsplit("/", 1)[0] if "/" in f else ""
        return any(o != f and (o.rsplit("/", 1)[0] if "/" in o else "") == folder and stem(o) == stem(f)
                   and mentions(report, o.rsplit("/", 1)[-1]) for o in changed)  # x.png + x.json come as a pair

    def strict(f, rel, in_project):
        if not near:
            return False
        parts = f.split("/")
        if in_project:
            named = mentions(near, rel) or mentions(near, parts[-1])
        else:  # outside the project a bare file name is too weak; a top-level file has only its own name
            named = any(mentions(near, "/".join(parts[i:])) for i in range(max(1, len(parts) - 1)))
        return named or any("/" in t and "*" in t and hit(t, rel) for t in near_ticks)

    ok, warn, bad = [], [], []
    for f in changed:
        if f == rep_path:
            ok.append(f)
            continue
        in_project = f.startswith(project) if project else True
        rel = f[len(project):] if project and in_project else f
        why, hard = None, True
        if not in_project:
            why = "프로젝트 폴더 밖"
        else:
            b = next((p for p in ban if hit(p, rel)), None)
            if b:
                why = f"카드의 금지(`{b}`)"
            elif not any(hit(p, rel) for p in allow):
                pair = re.search(r"(?:^|/)([^/]+)\.test\.\w+$", rel)
                a = next((x for x in alias_ban if hit(x[0], rel)), None)
                if a:
                    why = f"카드의 금지({a[1]})"
                elif not (pair and any(p.rsplit("/", 1)[-1].startswith(pair.group(1) + ".") for p in allow)):
                    why, hard = "카드 목록에 없음", False
        if why is None and any(hit(j, f) for j in cfg["judges"]):
            warn.append(f"{rel} — 판정기 변경(카드 안) · 관문은 HEAD 판으로 돌았음 — diff 를 읽을 것")
            continue
        if why is None:
            ok.append(f)
        elif (strict(f, rel, in_project) if hard else loose(f, rel)):
            warn.append(f"{rel} — {why} · 보고서에 적음")
        else:
            where_ = "보고서 엄격 칸(" + " · ".join(cfg["report"]["strict"]) + ")에 경로와" if hard else "보고서에 파일 이름과"
            bad.append(f"{rel} — {why} · 보고서에 없음 → 되돌리거나, 꼭 필요하면 {where_} 이유를 적을 것")

    rep_bad = []
    if report is None:
        rep_bad.append(f"보고서 {rep_path} 없음 — 보고서 틀대로 써서 같은 브랜치에 커밋할 것")
    else:
        heads = heads_of(report)
        missing = [s for s in cfg["report"]["sections"] if not any(re.search(s, h) for h in heads)]
        if missing:
            rep_bad.append("보고서 칸 빠짐: " + " · ".join(missing) + " — 없으면 \"없음\"이라고 적을 것")
        if cfg["report"].get("numbers_in"):
            body = part(report, cfg["report"]["numbers_in"])
            if body is not None and not re.search(r"\d", body):
                rep_bad.append("보고서 확인 칸에 숫자가 없음 — 실제로 돌린 명령과 결과 숫자를 적을 것")

    lines = [f"△ {s}" for s in warn] + [f"✘ {s}" for s in bad] + [f"✘ {s}" for s in rep_bad] + [f"· {s}" for s in notes]
    if unread:
        lines.append("· 말로만 쓴 금지(기계로 못 봄 — 사람이 볼 것): " + " · ".join(dict.fromkeys(unread)))
    n_fail = len(bad) + len(rep_bad)
    summary = f"바뀐 파일 {len(changed)} — 카드 안 {len(ok)} · △ {len(warn)} · ✘ {len(bad)} · 보고서 {'✘ ' + str(len(rep_bad)) if rep_bad else '✔'}"
    return lines, n_fail, summary


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for opt in ("--config", "--repo", "--branch", "--tip", "--into", "--card"):
        ap.add_argument(opt)
    ap.add_argument("--cards", help="card folder (overrides card.path and card.ref)")
    ap.add_argument("--worktree", action="store_true")
    ap.add_argument("--retro", action="store_true")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--soft", action="store_true")
    a = ap.parse_args(argv)
    repo = git(a.repo or os.getcwd(), "rev-parse", "--show-toplevel")
    cfg = load_config(a.config or Path(repo) / ".merge-gate" / "config.json")
    id_re = re.compile(cfg["card_id"])

    def done(code):
        sys.exit(0 if a.soft else code)

    if a.retro:
        rows = git(repo, "log", "--merges", "--first-parent", f"-n{a.limit}", "--format=%H %P%x09%s", cfg["guarded_branch"], check=False)
        if rows is None:
            print(f"✘ 지키는 브랜치 {cfg['guarded_branch']} 가 없음 — config.json 의 guarded_branch 를 확인할 것")
            done(2)
        total_fail = judged = 0
        for row in rows.splitlines():
            shas, subject = row.split("\t", 1)
            m, p1, *rest = shas.split()
            if not rest or not id_re.search(subject):
                continue
            card_id = id_re.search(subject).group(0)
            lines, n_fail, summary = judge(repo, cfg, card_id, tip=rest[-1], into=p1, cards_dir=a.cards)
            judged += 1
            total_fail += n_fail > 0
            print(f"{'✘' if n_fail else '✔'} {card_id} {m[:7]}: {summary}")
            for line in lines:
                if not line.startswith("·"):
                    print(f"    {line}")
        print(f"되짚기: 일꾼 합치기 {judged}번 · ✘ 난 합치기 {total_fail}번")
        done(1 if total_fail else 0)

    if a.worktree:
        br = git(repo, "branch", "--show-current") or ""
        m = re.match(cfg["worker_branch"], br)
        card_id = a.card or (m and m.group(1))
        if not card_id:
            print(f"· scope-check: 일꾼 브랜치가 아님({br or 'HEAD 떨어짐'}) — 건너뜀")
            sys.exit(0)
        lines, n_fail, summary = judge(repo, cfg, card_id, into=a.into or cfg["guarded_branch"], worktree=True, cards_dir=a.cards)
    else:
        tip = a.branch or a.tip
        card_id = a.card or (tip and id_re.search(tip) and id_re.search(tip).group(0))
        if not tip or not card_id:
            print("✘ 쓰는 법: --branch worker/T-012 | --tip <rev> --into <rev> --card T-012 | --worktree | --retro")
            done(2)
        lines, n_fail, summary = judge(repo, cfg, card_id, tip=tip, into=a.into or "HEAD", cards_dir=a.cards)
    for line in lines:
        print(line)
    print(f"{'✘' if n_fail else '✔'} scope-check {card_id}: {summary}")
    done(1 if n_fail else 0)


if __name__ == "__main__":
    main()
