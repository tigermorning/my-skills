"""Run one branch through checks -> headless review agent -> PR -> merge verdict, so a person only
reads the PRs the verdict sends them.

Usage (inside the repository, on a clean tree):
  python pr_pipeline.py run [--branch B] [--dry-run] [--no-review] [--config FILE]

Stages:
  1. preflight   branch is not the base, tree is clean, branch is ahead of the base
  2. checks      every command in config "checks" must exit 0 (stops here otherwise)
  3. review      `claude -p` reviews base...branch with the user-level and repo standards. It has no shell
                 and cannot edit the repository: it writes sure fixes as fix files, questions, and the PR body.
                 The pipeline commits each fix as "review: ...", runs the checks again and reverts review
                 commits that break them
     door        separate `claude -p` judges answer a fixed one-way checklist (door_runs times, default 3);
                 any yes makes the door one-way, and the pipeline writes the body's Merge Danger from it
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
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULTS = {
    "base": "main",
    "checks": [],
    "auto_merge": False,
    "max_changed_lines": 400,
    "protected_paths": [".github/"],
    "after_merge": [],
    "review": {"enabled": True, "max_turns": 40, "model": None, "timeout_sec": 1800, "door_runs": 3, "door_max_turns": 15},
    "ci_timeout_sec": 900,
}
# The review agent reads and writes only fix files and the body into its scratch directory; the pipeline
# applies the fixes and commits them. No shell: an allowed `python` or `node` could run `git push`.
REVIEW_TOOLS = ["Read", "Grep", "Glob"]
CHECK_OUTPUT_CHARS = 4000
REVIEW_DENY = ["Bash", "WebFetch", "WebSearch", "NotebookEdit"]


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
        out = (r.stdout + r.stderr).strip()
        # "tail" is for the run log; "output" is what the review agent reads as evidence. Three lines hid what
        # a green check covered, and the agent then asked whether the tests had run at all.
        results.append({"cmd": c, "code": r.returncode, "tail": out.splitlines()[-3:], "output": out[-CHECK_OUTPUT_CHARS:]})
    return results


def for_log(checks):
    return [{k: v for k, v in c.items() if k != "output"} for c in checks]


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


def scratch_rule(path):
    """Claude Code permission rule for writing under `path` only. Write calls are judged by Edit rules, and an
    absolute path is written with a leading // (C:/x becomes //c/x on Windows)."""
    p = Path(path).resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", p):
        p = "/" + p[0].lower() + p[2:]
    return f"Edit(/{p}/**)"


def review_prompt(base_ref, branch, scratch, body_path, standards, repo_standards, checks=()):
    std = "\n".join(f"- {p}" for p in [standards, repo_standards] if p) or "- (none; use the default list below)"
    fixes = scratch / "fixes"
    return f"""You are the review pass of a PR pipeline. No human is watching; work alone and finish.
Repository: the current directory. Branch: {branch}. Review the change {base_ref}...HEAD.
CHANGE_DIFF: {scratch / "change.diff"}
COMMITS: {scratch / "commits.txt"}
CHECKS_RUN: {scratch / "checks.txt"}
FIXES_DIR: {fixes}
BODY_PATH: {body_path}

Standards to enforce (the repository file wins over the user-level file):
{std}
If the standards-review skill is available, follow it. Default list: tests that lie (re-assert constants,
read source text instead of running, compare two implementations only, mocks that cannot fail), comments
that record history instead of reasons, dead code left behind, changes outside what the commits set out to do.

Rules:
1. You have no shell and cannot edit the repository. Read the files, CHANGE_DIFF and COMMITS; write only
   into FIXES_DIR and BODY_PATH.
2. Fix only what you are sure of, only in files CHANGE_DIFF touches, without changing behaviour. Write each
   fix as one JSON file in FIXES_DIR named 01.json, 02.json, ...:
   {{"subject": "review: <what>", "edits": [{{"path": "<path from the repository root>",
     "old": "<exact text that appears once in the file>", "new": "<replacement>"}}]}}
   The pipeline applies each fix as one commit. A fix whose old text is not found exactly once, or that
   touches another file, is dropped and becomes a question. Files under .claude/ are fine.
3. Anything you are not sure of becomes a question, not a fix.
4. After applying your fixes the pipeline runs these checks and reverts the fixes if they fail:
   {', '.join(checks) or '(none)'}. What they printed before your review is in CHECKS_RUN.
5. Write the PR body to BODY_PATH.
   Sections in order: "## Summary" (the smallest picture: pseudocode, call tree or file tree, plus a few lines),
   "## Evidence" (the commands in CHECKS_RUN and what they printed; you cannot run commands, so claim
   nothing else as run). Do not write "## Merge Danger": separate judges decide the door and the
   pipeline adds that section.
6. End your answer with one line of JSON and nothing after it:
   {{"title": "<PR title>", "questions": ["..."]}}
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


def denial_label(d):
    tool_input = d.get("tool_input") or {}
    if tool_input.get("file_path"):
        return str(tool_input["file_path"])
    if tool_input.get("command"):
        return f"{d.get('tool_name')}({str(tool_input['command'])[:80]})"
    return str(d.get("tool_name"))


def apply_fixes(repo, fixes_dir, scope):
    """Apply the agent's fix files in name order. Each becomes one commit or one question, never half of one."""
    root = Path(repo).resolve()
    commits, subjects, questions = [], [], []
    for f in sorted(Path(fixes_dir).glob("*.json")):
        try:
            fix = json.loads(f.read_text(encoding="utf-8-sig"))
            subject, edits = str(fix.get("subject") or "").strip(), fix.get("edits")
            if not subject or not isinstance(edits, list) or not edits:
                raise ValueError("needs a subject and at least one edit")
            texts = {}
            for e in edits:
                rel = str(e["path"]).replace("\\", "/").removeprefix("./")
                target = (root / rel).resolve()
                if rel not in scope or root not in target.parents:
                    raise ValueError(f"{rel} is not a file this change touches")
                text = texts[rel] if rel in texts else target.read_bytes().decode("utf-8")
                old, new = str(e["old"]), str(e["new"])
                if old == new:
                    raise ValueError(f"an edit in {rel} changes nothing")
                if "\r\n" in text and "\r\n" not in old:
                    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
                n = text.count(old) if old else 0
                if n != 1:
                    raise ValueError(f"old text appears {n} times in {rel}; it must appear exactly once")
                texts[rel] = text.replace(old, new, 1)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError, json.JSONDecodeError) as err:
            questions.append(f"fix {f.name} was not applied: {err}")
            continue
        for rel, text in texts.items():
            (root / rel).write_bytes(text.encode("utf-8"))
        subject = subject if subject.startswith("review:") else f"review: {subject}"
        git(repo, "add", "--", *texts)
        r = sh(["git", "commit", "-q", "-m", subject], repo, check=False)
        if r.returncode:
            git(repo, "restore", "--staged", "--worktree", "--", *texts)
            questions.append(f"fix {f.name} was not committed: {(r.stderr or r.stdout).strip()[:200]}")
            continue
        commits.append(git(repo, "rev-parse", "HEAD"))
        subjects.append(subject)
    return commits, subjects, questions


def review(repo, cfg, branch, base_ref, body_path, mdanger, checks_run=()):
    std = mdanger.find_user_standards()
    repo_std = Path(repo) / "CODING_STANDARDS.md"
    scratch = Path(tempfile.mkdtemp(prefix="pr-pipeline-")).resolve()
    try:
        return _review(repo, cfg, branch, base_ref, body_path, std, repo_std, scratch, checks_run)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _review(repo, cfg, branch, base_ref, body_path, std, repo_std, scratch, checks_run):
    (scratch / "fixes").mkdir()
    (scratch / "change.diff").write_text(git(repo, "diff", f"{base_ref}...HEAD"), encoding="utf-8")
    (scratch / "commits.txt").write_text(git(repo, "log", "--format=%h %s%n%n%b", f"{base_ref}..HEAD"), encoding="utf-8")
    (scratch / "checks.txt").write_text("\n\n".join(f"$ {c['cmd']}\nexit {c['code']}\n" + c.get("output", "\n".join(c["tail"]))
                                                   for c in checks_run) or "(no checks configured)", encoding="utf-8")
    draft = scratch / body_path.name
    # With the env the pipeline uses: the same command without it can fail for a local reason (check_skills
    # compares installed copies unless CI is set), and the agent then reports a failure that is not there.
    env = " ".join(f"{k}={v}" for k, v in (cfg.get("check_env") or {}).items())
    checks = [f"{env} {c}" if env else c for c in cfg["checks"]]
    prompt = review_prompt(base_ref, branch, scratch, draft, str(std) if std else None,
                           str(repo_std) if repo_std.is_file() else None, checks)
    # User settings only: the user's guard hooks still apply, but a repository's own hooks (a session
    # logger that commits on SessionEnd, for one) must not add commits to the branch under review.
    # Default permission mode: in -p anything not allowed below is refused, so the agent can read but only
    # write inside the scratch directory, and has no shell to reach git or the network through.
    args = [*cmd_from_env("PR_PIPELINE_CLAUDE", "claude"), "-p", "--output-format", "json", "--setting-sources", "user",
            "--permission-mode", "default", "--max-turns", str(cfg["review"]["max_turns"]), "--add-dir", str(scratch)]
    if std:
        args += ["--add-dir", str(Path(std).parent)]
    if cfg["review"].get("model"):
        args += ["--model", cfg["review"]["model"]]
    args += ["--disallowedTools", *REVIEW_DENY, "--allowedTools", *REVIEW_TOOLS, scratch_rule(scratch)]
    before = git(repo, "rev-parse", "HEAD")
    try:
        r = sh(args, repo, check=False, input_text=prompt, timeout=cfg["review"]["timeout_sec"])
    except subprocess.TimeoutExpired:
        raise StageError("review", f"review agent ran past {cfg['review']['timeout_sec']}s")
    if draft.is_file():
        shutil.copyfile(draft, body_path)
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
        raise StageError("review", "the tree changed during review; look at it before rerunning")
    # Commits made while the agent ran are not its own (it has no git); run() turns them into questions.
    foreign = git(repo, "rev-list", "--reverse", f"{before}..HEAD").split()
    questions = list(answer.get("questions") or [])
    denials = outer.get("permission_denials") if isinstance(outer, dict) else None
    denied = sorted({denial_label(d) for d in denials or [] if isinstance(d, dict)})
    if denied:
        questions.append("the review agent was refused permission for: " + ", ".join(denied))
    scope = set(changed_paths_and_lines(repo, base_ref)[0])
    commits, fixed, not_applied = apply_fixes(repo, scratch / "fixes", scope)
    return {"title": answer.get("title"), "questions": questions + not_applied, "fixed": fixed,
            "commits": foreign + commits, "answer_found": bool(answer)}


DOOR_CHECKS = {
    "data_loss": "When the merged code runs, it can delete or overwrite data or files people keep (not its own temp or build output).",
    "migration": "It changes a stored data format or schema in a way an old version cannot read back.",
    "outbound": "When the merged code runs, it sends something to other people or services: messages, emails, PR or issue comments, webhooks.",
    "publishing": "When the merged code runs, it pushes, deploys, releases or uploads something others can see.",
    "secrets": "It adds, moves or exposes credentials, tokens or keys.",
    "public_contract": "It removes, renames or changes the meaning of something others already rely on: CLI flags, file formats, "
                       "APIs, config keys. Adding a new optional one is not this.",
    "external_state": "When the merged code runs, it changes state outside this repository that a revert would not undo "
                      "(settings, accounts, remote branches, money).",
}


def door_prompt(diff_path, signals):
    items = "\n".join(f'- "{k}": {v}' for k, v in DOOR_CHECKS.items())
    hint = ", ".join(signals) or "(none)"
    shape = ", ".join(f'"{k}": {{"yes": false, "why": "..."}}' for k in DOOR_CHECKS)
    return f"""DOOR_JUDGE. You judge one thing about a change: whether merging it is a one-way door.
Read the diff at CHANGE_DIFF: {diff_path} and any repository file you need. You cannot run commands.

Judge what the merged code does when it runs, not the act of merging this change into this repository:
merging into a public repository is not by itself publishing, and a revert undoes a merge.
Answer every item yes or no, with a one-sentence reason quoting the code that decides it. Yes only when the
diff itself adds or changes the behaviour; a tool that already did it before this change is a no.
{items}

An automatic text scan of the diff flagged: {hint}. The scan matches words, so check each against the code.

Also give "blast_radius": one word for how far a mistake would reach (localized, module, users, data).
End with one line of JSON and nothing after it:
{{"checks": {{{shape}}}, "blast_radius": "<word>"}}
"""


def judge_door(repo, cfg, diff, signals):
    """Ask DOOR_CHECKS several times in parallel; any yes in any run makes the door one-way.
    A single holistic answer flipped between runs on the same diff; per-item answers with a conservative
    combine make the result stable, and the votes show where the judges disagreed."""
    runs = max(1, int(cfg["review"].get("door_runs", 3)))
    scratch = Path(tempfile.mkdtemp(prefix="pr-pipeline-door-")).resolve()
    try:
        diff_path = scratch / "change.diff"
        diff_path.write_text(diff, encoding="utf-8")
        prompt = door_prompt(diff_path, signals)
        args = [*cmd_from_env("PR_PIPELINE_CLAUDE", "claude"), "-p", "--output-format", "json", "--setting-sources", "user",
                "--permission-mode", "default", "--max-turns", str(cfg["review"].get("door_max_turns", 15)),
                "--add-dir", str(scratch)]
        if cfg["review"].get("model"):
            args += ["--model", cfg["review"]["model"]]
        args += ["--disallowedTools", *REVIEW_DENY, "--allowedTools", *REVIEW_TOOLS]
        with ThreadPoolExecutor(max_workers=runs) as pool:
            outs = list(pool.map(lambda _: sh(args, repo, check=False, input_text=prompt,
                                              timeout=cfg["review"]["timeout_sec"]), range(runs)))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    answers = []
    for r in outs:
        try:
            outer = json.loads(r.stdout)
        except json.JSONDecodeError:
            outer = {}
        if isinstance(outer, dict) and outer.get("is_error"):
            raise StageError("door", f"door judge failed: {str(outer.get('result'))[:300]}")
        ans = last_json(str(outer.get("result", "")) if isinstance(outer, dict) else "") or {}
        answers.append(ans if isinstance(ans.get("checks"), dict) else None)
    good = [a for a in answers if a]
    votes, why = {}, {}
    for k in DOOR_CHECKS:
        yes = [a["checks"].get(k) or {} for a in good if (a["checks"].get(k) or {}).get("yes") is True]
        votes[k] = len(yes)
        if yes:
            why[k] = str(yes[0].get("why") or "")[:200]
    missing = len(answers) - len(good)
    radii = [str(a.get("blast_radius") or "").strip().split()[0] for a in good if str(a.get("blast_radius") or "").strip()]
    radius = max(set(radii), key=radii.count) if radii else "unknown"
    one_way = missing > 0 or any(votes.values())
    if any(votes.values()):
        reason = "; ".join(f"{k} ({votes[k]}/{len(good)} judges): {why[k]}" for k in DOOR_CHECKS if votes[k])
    else:
        reason = f"none of {', '.join(DOOR_CHECKS)} holds ({len(good)}/{len(answers)} judges agree)"
    if missing:
        reason += f"; {missing} of {len(answers)} judges gave no usable answer, so one-way to be safe"
    return {"door": "one-way" if one_way else "two-way", "reason": reason, "radius": radius,
            "votes": votes, "runs": len(answers), "missing": missing}


def write_merge_danger(body_path, door):
    """Replace whatever Merge Danger the body has with the judged one."""
    body = body_path.read_text(encoding="utf-8-sig") if body_path.is_file() else ""
    body = re.split(r"(?mi)^##\s*merge danger\b", body)[0].rstrip()
    body += (f"\n\n## Merge Danger\n**Door:** {door['door']}\n**Reason:** {door['reason']}\n"
             f"**Blast radius:** {door['radius']}\n")
    body_path.write_text(body, encoding="utf-8")


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


def run(repo, cfg, branch=None, dry_run=False, no_review=False, title=None):
    mdanger = load_merge_danger()
    log = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "dry_run": dry_run}
    branch, base_ref = preflight(repo, cfg, branch)
    log.update(branch=branch, base=base_ref)
    state_dir = Path(git(repo, "rev-parse", "--absolute-git-dir")) / "pr-pipeline"
    state_dir.mkdir(exist_ok=True)
    body_path = state_dir / f"{re.sub(r'[^A-Za-z0-9._-]', '_', branch)}.md"

    checks = run_checks(repo, cfg["checks"], cfg.get("check_env"))
    log["checks"] = for_log(checks)
    if any(c["code"] for c in checks):
        raise StageError("checks", "failed: " + "; ".join(c["cmd"] for c in checks if c["code"]))

    rev = {"title": None, "questions": [], "fixed": [], "commits": []}
    if cfg["review"]["enabled"] and not no_review:
        scope = set(changed_paths_and_lines(repo, base_ref)[0])
        # A body left by an earlier run must not pass for one this review did not write.
        body_path.unlink(missing_ok=True)
        rev = review(repo, cfg, branch, base_ref, body_path, mdanger, checks)
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
        log["checks_after_review"] = for_log(again)
        if not rev["answer_found"]:
            rev["questions"].append("review agent did not end with the JSON line; read its commits by hand")
    log["review"] = rev
    if not body_path.is_file():
        raise StageError("body", f"no PR body at {body_path} (the review agent writes it; with --no-review write it yourself)")

    diff = git(repo, "diff", f"{base_ref}...HEAD")
    std = mdanger.find_user_standards()
    rules = mdanger.load_user_signals(std) if std else []
    repo_name = Path(git(repo, "rev-parse", "--show-toplevel")).name
    if cfg["review"]["enabled"] and not no_review:
        door = judge_door(repo, cfg, diff, mdanger.scan_signals(diff, rules, repo_name)[0])
        write_merge_danger(body_path, door)
        log["door"] = door
    body = body_path.read_text(encoding="utf-8-sig")
    report = mdanger.check(body, diff, rules, repo_name)
    _, user_hits = mdanger.scan_signals(diff, rules, repo_name)
    paths, nlines = changed_paths_and_lines(repo, base_ref)
    log.update(body=report, changed_lines=nlines, paths=paths)

    checks_ok = not any(c["code"] for c in log.get("checks_after_review", checks))
    pr, ci = None, "none"
    if not dry_run:
        title = title or rev.get("title") or git(repo, "log", "-1", "--format=%s", f"{base_ref}..HEAD")
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
    r.add_argument("--title", help="PR title (default: the review agent's, else the last commit subject)")
    r.add_argument("--config")
    r.add_argument("--repo", default=".")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        repo = git(a.repo, "rev-parse", "--show-toplevel")
        cfg = load_config(repo, a.config)
        log = run(repo, cfg, a.branch, a.dry_run, a.no_review, a.title)
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
