"""Run one branch through checks -> headless review agent -> PR -> merge verdict, so a person only
reads the PRs the verdict sends them.

Usage (inside the repository, on a clean tree):
  python pr_pipeline.py run [--branch B] [--dry-run] [--no-review] [--config FILE]

Stages:
  1. preflight   branch is not the base, tree is clean, branch is ahead of the base
  2. checks      every command in config "checks" must exit 0 (stops here otherwise)
  3. review      `claude -p` reviews base...branch with the user-level and repo standards, commits sure
                 fixes as "review: ...", leaves questions, and writes the PR body; checks run again and
                 review commits that break them are reverted
  4. body        the body must pass check_pr_body.py (pr-merge-danger) against the real diff
  5. publish     push the branch, create or update the PR, wait for CI   (skipped with --dry-run)
  6. verdict     auto-merge only if every condition holds; otherwise the PR stays open with the reasons.
                 With "auto_merge": false the verdict is reported and a person says when to merge.

Config: <repo>/.claude/pr-pipeline.json (see config.example.json). Commands can be replaced for tests with
PR_PIPELINE_CLAUDE / PR_PIPELINE_GH holding a JSON list, e.g. ["python", "fake_gh.py"].
Exit codes: 0 = pipeline finished (read the verdict), 1 = a stage failed, 2 = usage or setup error.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULTS = {
    "base": "main",
    "checks": [],
    "auto_merge": False,
    "max_changed_lines": 400,
    "protected_paths": [".github/"],
    "after_merge": [],
    "review": {"enabled": True, "max_turns": 40, "model": None, "timeout_sec": 1800},
    "ci_timeout_sec": 900,
}
REVIEW_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
                "Bash(git status:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(python:*)", "Bash(node:*)"]
REVIEW_DENY = ["Bash(git push:*)", "Bash(git reset:*)", "Bash(git rebase:*)", "Bash(git checkout:*)", "WebFetch", "WebSearch"]


class StageError(Exception):
    def __init__(self, stage, msg, code=1):
        super().__init__(f"{stage}: {msg}")
        self.stage, self.code = stage, code


def cmd_from_env(name, default):
    raw = os.environ.get(name)
    return json.loads(raw) if raw else [default]


def sh(args, cwd, check=True, input_text=None, timeout=None):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       input=input_text, timeout=timeout)
    if check and r.returncode != 0:
        raise StageError("git" if args[0] == "git" else Path(str(args[0])).name,
                         f"{' '.join(map(str, args))} -> {r.returncode}: {(r.stderr or r.stdout).strip()[:400]}")
    return r


def git(repo, *args, check=True):
    return sh(["git", *args], repo, check=check).stdout.strip()


def load_merge_danger():
    """check_pr_body.py from the sibling pr-merge-danger skill (repo checkout or ~/.claude/skills)."""
    for p in (HERE.parent.parent / "pr-merge-danger" / "scripts" / "check_pr_body.py",
              Path.home() / ".claude" / "skills" / "pr-merge-danger" / "scripts" / "check_pr_body.py"):
        if p.is_file():
            spec = importlib.util.spec_from_file_location("check_pr_body", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise StageError("setup", "pr-merge-danger skill (check_pr_body.py) not found next to this skill or in ~/.claude/skills", 2)


def load_config(repo, path=None):
    p = Path(path) if path else Path(repo) / ".claude" / "pr-pipeline.json"
    if not p.is_file():
        raise StageError("setup", f"no config at {p} (copy config.example.json there)", 2)
    cfg = {**DEFAULTS, **json.loads(p.read_text(encoding="utf-8-sig"))}
    cfg["review"] = {**DEFAULTS["review"], **cfg.get("review", {})}
    return cfg


def run_checks(repo, commands, extra_env=None):
    results = []
    env = {**os.environ, **{k: str(v) for k, v in (extra_env or {}).items()}}
    for c in commands:
        r = subprocess.run(c, cwd=repo, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        results.append({"cmd": c, "code": r.returncode, "tail": tail})
    return results


def preflight(repo, cfg, branch):
    cur = git(repo, "branch", "--show-current")
    branch = branch or cur
    if not branch or branch == cfg["base"]:
        raise StageError("preflight", f"run it on a feature branch, not '{branch or 'detached HEAD'}'", 2)
    if git(repo, "status", "--porcelain"):
        raise StageError("preflight", "working tree is not clean; commit or stash first", 2)
    if cur != branch:
        git(repo, "switch", branch)
    git(repo, "fetch", "--quiet", "origin", cfg["base"], check=False)
    base_ref = f"origin/{cfg['base']}" if git(repo, "rev-parse", "--verify", "--quiet", f"origin/{cfg['base']}", check=False) else cfg["base"]
    ahead = int(git(repo, "rev-list", "--count", f"{base_ref}..{branch}") or 0)
    if ahead == 0:
        raise StageError("preflight", f"{branch} has no commits ahead of {base_ref}", 2)
    return branch, base_ref


def review_prompt(base_ref, branch, body_path, standards, repo_standards):
    std = "\n".join(f"- {p}" for p in [standards, repo_standards] if p) or "- (none; use the default list below)"
    return f"""You are the review pass of a PR pipeline. No human is watching; work alone and finish.
Repository: the current directory. Branch: {branch}. Review the change {base_ref}...HEAD.

Standards to enforce (the repository file wins over the user-level file):
{std}
If the standards-review skill is available, follow it. Default list: tests that lie (re-assert constants,
read source text instead of running, compare two implementations only, mocks that cannot fail), comments
that record history instead of reasons, dead code left behind, changes outside what the commits set out to do.

Rules:
1. Fix only what you are sure of, only in files this change already touches, without changing behaviour.
   Commit each fix with `git commit -m "review: <what>"`. Never push, reset, rebase or switch branches.
2. Anything you are not sure of becomes a question, not a fix.
3. Run the repository's quick checks after fixing if you know them.
4. Write the PR body to BODY_PATH: {body_path}
   Sections in order: "## Summary" (the smallest picture: pseudocode, call tree or file tree, plus a few lines),
   "## Evidence" (commands that were run and what they printed — run them yourself), "## Merge Danger" with
   "**Door:** one-way|two-way", "**Reason:** <why>" and "**Blast radius:** <one word>". Judge Door honestly:
   data loss, migrations, outbound messages, publishing, secrets, public contracts are one-way.
5. End your answer with one line of JSON and nothing after it:
   {{"title": "<PR title>", "questions": ["..."], "fixed": ["<commit subject>"]}}
"""


def last_json(text):
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def review(repo, cfg, branch, base_ref, body_path, mdanger):
    std = mdanger.find_user_standards()
    repo_std = Path(repo) / "CODING_STANDARDS.md"
    prompt = review_prompt(base_ref, branch, body_path, str(std) if std else None, str(repo_std) if repo_std.is_file() else None)
    # User settings only: the user's guard hooks still apply, but a repository's own hooks (a session
    # logger that commits on SessionEnd, for one) must not add commits to the branch under review.
    args = [*cmd_from_env("PR_PIPELINE_CLAUDE", "claude"), "-p", "--output-format", "json", "--setting-sources", "user",
            "--permission-mode", "acceptEdits", "--max-turns", str(cfg["review"]["max_turns"])]
    if std:
        args += ["--add-dir", str(Path(std).parent)]
    if cfg["review"].get("model"):
        args += ["--model", cfg["review"]["model"]]
    args += ["--disallowedTools", *REVIEW_DENY, "--allowedTools", *REVIEW_TOOLS]
    before = git(repo, "rev-parse", "HEAD")
    try:
        r = sh(args, repo, check=False, input_text=prompt, timeout=cfg["review"]["timeout_sec"])
    except subprocess.TimeoutExpired:
        raise StageError("review", f"review agent ran past {cfg['review']['timeout_sec']}s")
    try:
        outer = json.loads(r.stdout)
    except json.JSONDecodeError:
        outer = None
    if isinstance(outer, dict) and outer.get("is_error"):
        msg = str(outer.get("result") or "")
        hint = " — log in again: run `claude` in a terminal and use /login" if re.search(r"auth|login|OAuth", msg, re.I) else ""
        raise StageError("review", f"review agent failed: {msg[:300]}{hint}")
    if r.returncode != 0:
        raise StageError("review", f"review agent exit {r.returncode}: {(r.stderr or r.stdout).strip()[:400]}")
    text = outer.get("result", "") if isinstance(outer, dict) else r.stdout
    answer = last_json(text) or {}
    if git(repo, "status", "--porcelain"):
        raise StageError("review", "review agent left uncommitted changes; look at the tree before rerunning")
    commits = git(repo, "rev-list", "--reverse", f"{before}..HEAD").split()
    return {"title": answer.get("title"), "questions": list(answer.get("questions") or []),
            "fixed": list(answer.get("fixed") or []), "commits": commits, "answer_found": bool(answer)}


def changed_paths_and_lines(repo, base_ref):
    paths, lines = [], 0
    for row in git(repo, "diff", "--numstat", f"{base_ref}...HEAD").splitlines():
        add, rem, path = row.split("\t", 2)
        paths.append(path)
        lines += (int(add) if add.isdigit() else 0) + (int(rem) if rem.isdigit() else 0)
    return paths, lines


def decide(cfg, *, checks_ok, ci, body_report, questions, user_blocks, changed_lines, paths):
    """Pure verdict: (auto_merge_ok, reasons). Every unmet condition is listed so a person sees why."""
    reasons = []
    if not checks_ok:
        reasons.append("local checks failed")
    if ci not in ("success", "none"):
        reasons.append(f"CI is {ci}")
    if not body_report["ok"]:
        reasons.append("PR body: " + "; ".join(body_report["problems"]))
    if body_report.get("door") != "two-way":
        reasons.append(f"door is {body_report.get('door')}, not two-way")
    if body_report.get("one_way_signals"):
        reasons.append("one-way signals in the diff: " + ", ".join(body_report["one_way_signals"]))
    if user_blocks:
        reasons.append("blocked by your one-way rules")
    if questions:
        reasons.append(f"review left {len(questions)} question(s)")
    if changed_lines > cfg["max_changed_lines"]:
        reasons.append(f"{changed_lines} changed lines > {cfg['max_changed_lines']}")
    hit = [p for p in paths for pp in cfg["protected_paths"] if p == pp or p.startswith(pp)]
    if hit:
        reasons.append("touches protected paths: " + ", ".join(sorted(set(hit))))
    return not reasons, reasons


def gh(args, repo, check=True):
    return sh([*cmd_from_env("PR_PIPELINE_GH", "gh"), *args], repo, check=check)


def publish(repo, cfg, branch, title, body_path):
    git(repo, "push", "--quiet", "-u", "origin", branch)
    view = gh(["pr", "view", branch, "--json", "number,url"], repo, check=False)
    if view.returncode == 0 and view.stdout.strip():
        pr = json.loads(view.stdout)
        gh(["pr", "edit", str(pr["number"]), "--body-file", str(body_path)], repo)
        return pr
    out = gh(["pr", "create", "--base", cfg["base"], "--head", branch, "--title", title, "--body-file", str(body_path)], repo).stdout
    url = out.strip().splitlines()[-1]
    return {"number": int(re.search(r"/pull/(\d+)", url).group(1)), "url": url}


def wait_ci(repo, number, timeout):
    """'success', 'failure', 'pending' (timed out) or 'none' (the repository runs no checks)."""
    start = time.time()
    # GitHub takes a few seconds to register a run; only after this grace does "no checks" mean none exist.
    grace = float(os.environ.get("PR_PIPELINE_CI_GRACE", "30"))
    end = start + timeout
    while True:
        r = gh(["pr", "checks", str(number), "--json", "bucket"], repo, check=False)
        rows = json.loads(r.stdout) if r.stdout.strip().startswith("[") else []
        buckets = [x.get("bucket") for x in rows]
        if not buckets:
            if time.time() - start >= grace:
                return "none"
        elif any(b in ("fail", "cancel") for b in buckets):
            return "failure"
        elif all(b in ("pass", "skipping") for b in buckets):
            return "success"
        if time.time() > end:
            return "pending"
        time.sleep(float(os.environ.get("PR_PIPELINE_POLL", "15")))


def verdict_comment(ok, reasons, auto, merged):
    head = ("자동 머지함" if merged else "자동 머지 조건 충족 — auto_merge 가 꺼져 있어 사람이 머지를 정함" if ok
            else "자동 머지하지 않음 — 사람이 볼 것")
    lines = [f"**pr-pipeline 판정**: {head}", ""]
    lines += [f"- {r}" for r in reasons] or ["- 모든 조건 충족: 검사·CI 초록, two-way, 위험 신호 없음, 리뷰 질문 0, 크기·보호 경로 통과"]
    if ok and not auto:
        lines += ["", "머지하려면: `gh pr merge <번호> --merge`"]
    return "\n".join(lines)


def run(repo, cfg, branch=None, dry_run=False, no_review=False):
    mdanger = load_merge_danger()
    log = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "dry_run": dry_run}
    branch, base_ref = preflight(repo, cfg, branch)
    log.update(branch=branch, base=base_ref)
    state_dir = Path(git(repo, "rev-parse", "--absolute-git-dir")) / "pr-pipeline"
    state_dir.mkdir(exist_ok=True)
    body_path = state_dir / f"{re.sub(r'[^A-Za-z0-9._-]', '_', branch)}.md"

    checks = run_checks(repo, cfg["checks"], cfg.get("check_env"))
    log["checks"] = checks
    if any(c["code"] for c in checks):
        raise StageError("checks", "failed: " + "; ".join(c["cmd"] for c in checks if c["code"]))

    rev = {"title": None, "questions": [], "fixed": [], "commits": []}
    if cfg["review"]["enabled"] and not no_review:
        scope = set(changed_paths_and_lines(repo, base_ref)[0])
        rev = review(repo, cfg, branch, base_ref, body_path, mdanger)
        for c in rev["commits"]:
            subject = git(repo, "log", "-1", "--format=%s", c)
            if not subject.startswith("review:"):
                rev["questions"].append(f"commit {c[:7]} '{subject[:60]}' appeared during review but is not a review fix")
            outside = [p for p in git(repo, "show", "--name-only", "--format=", c).splitlines() if p and p not in scope]
            if outside:
                rev["questions"].append(f"review commit {c[:7]} touched files outside the change: {', '.join(outside)}")
        again = run_checks(repo, cfg["checks"], cfg.get("check_env"))
        if any(c["code"] for c in again) and rev["commits"]:
            for c in reversed(rev["commits"]):
                git(repo, "revert", "--no-edit", c)
            rev["questions"].append("review fixes broke the checks and were reverted: " + ", ".join(rev["commits"]))
            again = run_checks(repo, cfg["checks"], cfg.get("check_env"))
        log["checks_after_review"] = again
        if not rev["answer_found"]:
            rev["questions"].append("review agent did not end with the JSON line; read its commits by hand")
    log["review"] = rev
    if not body_path.is_file():
        raise StageError("body", f"no PR body at {body_path} (the review agent writes it; with --no-review write it yourself)")

    diff = git(repo, "diff", f"{base_ref}...HEAD")
    std = mdanger.find_user_standards()
    rules = mdanger.load_user_signals(std) if std else []
    repo_name = Path(git(repo, "rev-parse", "--show-toplevel")).name
    body = body_path.read_text(encoding="utf-8-sig")
    report = mdanger.check(body, diff, rules, repo_name)
    hits, user_hits = mdanger._scan(diff, rules, repo_name)
    paths, nlines = changed_paths_and_lines(repo, base_ref)
    log.update(body=report, changed_lines=nlines, paths=paths)

    checks_ok = not any(c["code"] for c in log.get("checks_after_review", checks))
    pr, ci = None, "none"
    if not dry_run:
        title = rev.get("title") or git(repo, "log", "-1", "--format=%s", f"{base_ref}..HEAD")
        pr = publish(repo, cfg, branch, title, body_path)
        ci = wait_ci(repo, pr["number"], cfg["ci_timeout_sec"])
    ok, reasons = decide(cfg, checks_ok=checks_ok, ci=ci, body_report=report, questions=rev["questions"],
                         user_blocks=[u["label"] for u in user_hits if u["block"]], changed_lines=nlines, paths=paths)
    merged = False
    if pr and ok and cfg["auto_merge"]:
        git(repo, "switch", cfg["base"])
        gh(["pr", "merge", str(pr["number"]), "--merge"], repo)
        merged = True
        for c in cfg["after_merge"]:
            subprocess.run(c.replace("{branch}", branch), cwd=repo, shell=True)
    if pr:
        gh(["pr", "comment", str(pr["number"]), "--body", verdict_comment(ok, reasons, cfg["auto_merge"], merged)], repo, check=False)
    log.update(pr=pr, ci=ci, auto_merge_ok=ok, reasons=reasons, merged=merged)
    (state_dir / f"{body_path.stem}.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--branch")
    r.add_argument("--dry-run", action="store_true", help="stop before push: checks, review, body and a verdict without CI")
    r.add_argument("--no-review", action="store_true", help="skip the review agent (the body must already exist)")
    r.add_argument("--config")
    r.add_argument("--repo", default=".")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        repo = git(a.repo, "rev-parse", "--show-toplevel")
        cfg = load_config(repo, a.config)
        log = run(repo, cfg, a.branch, a.dry_run, a.no_review)
    except StageError as e:
        print(f"STOP {e}", file=sys.stderr)
        return e.code
    if a.json:
        print(json.dumps(log, ensure_ascii=False, indent=2))
    else:
        rev = log["review"]
        print(f"branch={log['branch']} base={log['base']} changed_lines={log['changed_lines']} ci={log['ci']}")
        print(f"review: {len(rev['commits'])} fix commit(s), {len(rev['questions'])} question(s)")
        for q in rev["questions"]:
            print(f"  ? {q}")
        print(f"door={log['body'].get('door')} signals={log['body'].get('one_way_signals')}")
        print("VERDICT " + ("auto-merge ok" if log["auto_merge_ok"] else "needs a person") + (" (merged)" if log["merged"] else "")
              + (" (dry-run: not pushed, CI not checked)" if log["dry_run"] else ""))
        for x in log["reasons"]:
            print(f"  - {x}")
        if log.get("pr"):
            print(f"PR {log['pr']['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
