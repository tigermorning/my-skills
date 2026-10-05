"""Self-test for pr_pipeline.py with a bare origin, a fake `claude` and a fake `gh`. Run: python test_pr_pipeline.py"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
spec = importlib.util.spec_from_file_location("pr_pipeline", HERE / "pr_pipeline.py")
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)

GOOD_BODY = """## Summary
```
app.add(x)  # new helper
```

## Evidence
- `python check.py` -> ok

## Merge Danger
**Door:** two-way
**Reason:** a new helper only; revert removes it
**Blast radius:** localized
"""

FAKE_CLAUDE = r'''
import json, os, re, shutil, subprocess, sys
prompt = sys.stdin.buffer.read().decode("utf-8")
log = os.environ["FAKE_CLAUDE_LOG"]
if "DOOR_JUDGE" in prompt:
    # Judges run in parallel; appends to one file from several processes can lose lines on Windows.
    open(f"{log}.door-{os.getpid()}", "w", encoding="utf-8").write(" ".join(sys.argv[1:]))
    door = os.environ.get("FAKE_DOOR", "two-way")
    if door == "split":
        try:
            os.close(os.open(log + ".door-yes", os.O_CREAT | os.O_EXCL))
            door = "one-way"
        except FileExistsError:
            door = "two-way"
    if door == "garbage":
        print(json.dumps({"type": "result", "result": "no idea"}))
        sys.exit(0)
    items = ["data_loss", "migration", "outbound", "publishing", "secrets", "public_contract", "external_state"]
    checks = {k: {"yes": door == "one-way" and k == "outbound", "why": "posts a comment" if k == "outbound" else "no"} for k in items}
    print(json.dumps({"type": "result", "result": "ok\n" + json.dumps({"checks": checks, "blast_radius": "localized"})}))
    sys.exit(0)
open(log, "a", encoding="utf-8").write("called\n")
open(log + ".prompt", "w", encoding="utf-8").write(prompt)
field = lambda name: re.search(name + r": (.+)", prompt).group(1).strip()
body_path, fixes = field("BODY_PATH"), field("FIXES_DIR")
shutil.copyfile(field("CHANGE_DIFF"), log + ".diff")
shutil.copyfile(field("CHECKS_RUN"), log + ".checks")
open(log, "a", encoding="utf-8").write("BODY " + body_path + "\n")
mode = os.environ.get("FAKE_REVIEW", "clean")
open(log, "a", encoding="utf-8").write(" ".join(sys.argv[1:]) + "\n")
if mode == "autherror":
    print(json.dumps({"type": "result", "is_error": True, "result": "Failed to authenticate: OAuth session expired"}))
    sys.exit(1)
def fix(name, subject, path, old, new):
    edit = {"path": path, "old": old, "new": new}
    open(os.path.join(fixes, name), "w", encoding="utf-8").write(json.dumps({"subject": subject, "edits": [edit]}))
questions = []
if mode == "fix":
    fix("01.json", "review: tidy helper", "app.py", "    return x + 1\n", "    return x + 1  # one past x\n")
if mode == "two":
    fix("01.json", "review: first", "app.py", "def add(x):", "def add(x):  # helper")
    fix("02.json", "review: missing", "app.py", "no such text", "x")
if mode == "break":
    fix("01.json", "review: oops", "app.py", "    return x + 1\n", "    return x + 1  # BROKEN\n")
if mode == "ambiguous":
    fix("01.json", "review: which return", "app.py", "    return", "    return  # x")
if mode == "outside":
    fix("01.json", "review: touch check", "check.py", "import os", "import os  # x")
if mode == "escape":
    fix("01.json", "review: escape", "../outside.py", "x", "y")
if mode == "dotclaude":
    fix("01.json", "tidy skill", ".claude/skills/a/x.py", "x = 1", "x = 1  # one")
if mode == "foreign":
    with open("app.py", "a", encoding="utf-8") as f:
        f.write("# session log\n")
    subprocess.run(["git", "commit", "-qam", "project-session-memory: capture session x"], check=True)
if mode == "dirty":
    open("app.py", "a", encoding="utf-8").write("# left behind\n")
if mode == "question":
    questions.append("is the helper meant to be public?")
body = os.environ.get("FAKE_BODY") or GOOD
if mode != "nobody":
    open(body_path, "w", encoding="utf-8").write(body)
answer = {"title": "Add helper", "questions": questions}
if mode == "nojson":
    print(json.dumps({"type": "result", "result": "done, no json line"}))
elif mode == "denied":
    print(json.dumps({"type": "result", "result": "done\n" + json.dumps(answer), "permission_denials": [
        {"tool_name": "Edit", "tool_input": {"file_path": ".claude/skills/a/x.py"}},
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}]}))
else:
    print(json.dumps({"type": "result", "result": "done\n" + json.dumps(answer)}))
'''.replace("GOOD", repr(GOOD_BODY), 1)

FAKE_GH = r'''
import json, os, sys
args = sys.argv[1:]
open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8").write(json.dumps(args) + "\n")
if args[:2] == ["pr", "view"]:
    sys.exit(1)
if args[:2] == ["pr", "create"]:
    print("https://github.com/o/r/pull/7")
if args[:2] == ["pr", "checks"]:
    print(os.environ.get("FAKE_CI", "[]"))
'''


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def make_repo(d, cfg_over=None, branch_files=None):
    d = Path(d)
    origin, work = d / "origin.git", d / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "t")
    (work / "check.py").write_text("import os, sys\nsys.exit(1 if os.path.exists('FAIL') or 'BROKEN' in open('app.py').read() else 0)\n",
                                   encoding="utf-8")
    (work / "app.py").write_text("def app():\n    return 1\n", encoding="utf-8")
    cfg = {"base": "main", "checks": [f'"{PY}" check.py'], "auto_merge": False, "max_changed_lines": 400,
           "protected_paths": [".github/"], "ci_timeout_sec": 5, "review": {"enabled": True, "max_turns": 5, "timeout_sec": 60}}
    cfg.update(cfg_over or {})
    (work / ".claude").mkdir()
    (work / ".claude" / "pr-pipeline.json").write_text(json.dumps(cfg), encoding="utf-8")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "init")
    git(work, "push", "-q", "-u", "origin", "main")
    git(work, "switch", "-q", "-c", "feat/x")
    for name, text in (branch_files or {"app.py": "def app():\n    return 1\n\ndef add(x):\n    return x + 1\n"}).items():
        p = work / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "feat: add helper")
    return work, origin


def pipeline(work, d, args=(), **env_over):
    d = Path(d)
    (d / "fake_claude.py").write_text(FAKE_CLAUDE, encoding="utf-8")
    (d / "fake_gh.py").write_text(FAKE_GH, encoding="utf-8")
    env = {**os.environ, "PR_PIPELINE_CLAUDE": json.dumps([PY, str(d / "fake_claude.py")]),
           "PR_PIPELINE_GH": json.dumps([PY, str(d / "fake_gh.py")]), "FAKE_GH_LOG": str(d / "gh.log"),
           "FAKE_CLAUDE_LOG": str(d / "claude.log"), "PR_PIPELINE_POLL": "0", "PR_PIPELINE_CI_GRACE": "0",
           "REVIEW_STANDARDS": "", "FAKE_CI": '[{"bucket": "pass"}]', **env_over}
    r = subprocess.run([PY, str(HERE / "pr_pipeline.py"), "run", "--json", *args], cwd=work, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip().startswith("{") else None
    gh_calls = [json.loads(l) for l in (d / "gh.log").read_text(encoding="utf-8").splitlines()] if (d / "gh.log").exists() else []
    return r.returncode, log, r.stderr, gh_calls, (d / "claude.log").exists()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    failed = []

    def case(name, cfg=None, files=None, args=(), want_code=0, want_ok=None, reason=None, check=None, before=None, **env):
        with tempfile.TemporaryDirectory() as d:
            work, origin = make_repo(d, cfg, files)
            if before:
                before(work)
            code, log, err, calls, claude_called = pipeline(work, d, args, **env)
            problems = []
            if code != want_code:
                problems.append(f"exit {code} != {want_code} ({err.strip()[:200]})")
            if log and want_ok is not None and log["auto_merge_ok"] != want_ok:
                problems.append(f"auto_merge_ok {log['auto_merge_ok']} != {want_ok}: {log['reasons']}")
            if log and reason and not any(reason in x for x in log["reasons"]):
                problems.append(f"no reason containing {reason!r}: {log['reasons']}")
            if check and (log is not None or want_code != 0):
                problems += check(work, origin, log, err, calls, claude_called) or []
            if problems:
                failed.append(f"{name}: " + " | ".join(problems))

    def no_push(work, origin, log, err, calls, claude_called):
        return [] if not git(origin, "branch", "--list", "feat/x") else ["dry-run pushed the branch"]

    def judged_not_merged(work, origin, log, err, calls, claude_called):
        out = []
        if not any(c[:2] == ["pr", "create"] for c in calls):
            out.append("no PR created")
        if any(c[:2] == ["pr", "merge"] for c in calls):
            out.append("merged although auto_merge is off")
        if not any(c[:2] == ["pr", "comment"] and "판정" in c[-1] for c in calls):
            out.append("no verdict comment")
        return out

    def merged(work, origin, log, err, calls, claude_called):
        return [] if any(c[:2] == ["pr", "merge"] for c in calls) and log["merged"] else ["auto_merge on but not merged"]

    def reverted(work, origin, log, err, calls, claude_called):
        out = []
        if "BROKEN" in (Path(work) / "app.py").read_text(encoding="utf-8"):
            out.append("breaking review commit still in the tree")
        if not any("reverted" in q for q in log["review"]["questions"]):
            out.append("no question about the revert")
        return out

    def no_review_call(work, origin, log, err, calls, claude_called):
        return ["review ran although checks failed first"] if claude_called else []

    case("dry-run clean", args=["--dry-run"], want_ok=True, check=no_push)
    case("judge only, clean, CI pass", want_ok=True, check=judged_not_merged)
    case("auto-merge when everything holds", cfg={"auto_merge": True}, want_ok=True, check=merged)
    case("review question blocks", want_ok=False, reason="question", FAKE_REVIEW="question")
    def fix_committed(work, origin, log, err, calls, claude_called):
        out = []
        if len(log["review"]["commits"]) != 1 or log["review"]["fixed"] != ["review: tidy helper"]:
            out.append(f"fix not committed once: {log['review']}")
        if git(work, "log", "-1", "--format=%s") != "review: tidy helper":
            out.append("last commit is not the review fix")
        data = (Path(work) / "app.py").read_bytes()
        if b"one past x" not in data:
            out.append("fix text not in the file")
        if b"\r\n" in data and data.count(b"\n") != data.count(b"\r\n"):
            out.append("fix mixed LF into a CRLF file")
        return out
    case("the pipeline commits the agent's fix file", want_ok=True, FAKE_REVIEW="fix", check=fix_committed)
    case("review fix that breaks checks is reverted", want_ok=False, FAKE_REVIEW="break", check=reverted)
    no_commits = lambda w, o, log, *a: [] if not log["review"]["commits"] else ["a fix was committed although it should be dropped"]
    case("a fix to a file outside the change is dropped as a question", want_ok=False, reason="question", FAKE_REVIEW="outside",
         check=lambda w, o, log, *a: no_commits(w, o, log) + ([] if any("not a file this change touches" in q for q in log["review"]["questions"]) else ["no question"]))
    case("a fix whose old text appears twice is dropped", want_ok=False, reason="question", FAKE_REVIEW="ambiguous",
         check=lambda w, o, log, *a: no_commits(w, o, log) + ([] if any("2 times" in q for q in log["review"]["questions"]) else ["no question"]))
    case("a fix path leaving the repository is dropped",want_ok=False, reason="question", FAKE_REVIEW="escape", check=no_commits)
    case("of two fixes the one that does not match is dropped, the other committed", want_ok=False, reason="question", FAKE_REVIEW="two",
         check=lambda w, o, log, *a: [] if log["review"]["fixed"] == ["review: first"] and any("02.json" in q and "0 times" in q for q in log["review"]["questions"])
         else [f"wrong split: {log['review']}"])
    case("a fix under .claude/ is committed by the pipeline", want_ok=True, FAKE_REVIEW="dotclaude",
         files={"app.py": "def app():\n    return 1\n\ndef add(x):\n    return x + 1\n", ".claude/skills/a/x.py": "x = 1\n"},
         check=lambda w, o, log, *a: [] if log["review"]["fixed"] == ["review: tidy skill"] and "# one" in (Path(w) / ".claude/skills/a/x.py").read_text(encoding="utf-8")
         else [f"fix under .claude/ not committed: {log['review']}"])
    case("review leaving a dirty tree stops", want_code=1, FAKE_REVIEW="dirty")
    case("a non-review commit during review becomes a question", want_ok=False, reason="question", FAKE_REVIEW="foreign",
         check=lambda w, o, log, *a: [] if any("not a review fix" in q for q in log["review"]["questions"]) else ["foreign commit not flagged"])
    case("expired login stops with the agent's own message", want_code=1, FAKE_REVIEW="autherror",
         check=lambda w, o, log, err, *a: [] if "OAuth session expired" in err and "/login" in err else [f"message lost: {err[:200]}"])

    def user_settings_only(work, origin, log, err, calls, claude_called):
        args = (Path(work).parent / "claude.log").read_text(encoding="utf-8")
        return [] if "--setting-sources user" in args else ["review agent not limited to user settings (repo hooks would run)"]
    case("review agent runs with user settings only", want_ok=True, check=user_settings_only)

    def no_shell(work, origin, log, err, calls, claude_called):
        lines = (Path(work).parent / "claude.log").read_text(encoding="utf-8").splitlines()
        args = next(l for l in lines if l.startswith("-p "))
        body = next(l[5:] for l in lines if l.startswith("BODY "))
        allowed = args.split("--allowedTools", 1)[1]
        out = []
        if "--permission-mode default" not in args:
            out.append("not in default permission mode (acceptEdits lets the agent edit the repository)")
        if "--disallowedTools Bash " not in args or "Bash" in allowed:
            out.append(f"the agent can still use a shell: {args}")
        scratch = Path(body).parent.as_posix()
        if not any(t.startswith("Edit(//") and t.rstrip(")").endswith("/**") and scratch.split("/")[-1] in t for t in allowed.split()):
            out.append(f"no write rule limited to the scratch directory: {allowed}")
        return out
    case("review agent has no shell and writes only to its scratch directory", want_ok=True, check=no_shell)

    def given_diff_and_checks(work, origin, log, err, calls, claude_called):
        d = Path(work).parent
        out = []
        if "def add(x)" not in (d / "claude.log.diff").read_text(encoding="utf-8"):
            out.append("the change diff given to the agent lacks the change")
        if "check.py" not in (d / "claude.log.checks").read_text(encoding="utf-8"):
            out.append("the agent was not given what the checks printed")
        return out
    case("review agent gets the diff and the check output as files", want_ok=True, check=given_diff_and_checks)
    case("no body stops", want_code=1, FAKE_REVIEW="nobody")

    def stale_body(work):
        state = Path(git(work, "rev-parse", "--absolute-git-dir")) / "pr-pipeline"
        state.mkdir()
        (state / "feat_x.md").write_text(GOOD_BODY, encoding="utf-8")
    case("a body left by an earlier run does not pass for this review", want_code=1, FAKE_REVIEW="nobody", before=stale_body)

    def body_outside_git(work, origin, log, err, calls, claude_called):
        lines = (Path(work).parent / "claude.log").read_text(encoding="utf-8").splitlines()
        body = next(l[5:] for l in lines if l.startswith("BODY "))
        args = next(l for l in lines if l.startswith("-p "))
        out = []
        if ".git" in Path(body).parts:
            out.append(f"review agent told to write the body under .git (Claude Code blocks it): {body}")
        if f"--add-dir {Path(body).parent}" not in args:
            out.append("the body's directory is not given to the agent with --add-dir")
        return out
    case("review agent writes the body where it is allowed to", want_ok=True, check=body_outside_git)
    case("an edit the agent was refused becomes a question", want_ok=False, reason="question", FAKE_REVIEW="denied",
         check=lambda w, o, log, *a: [] if any(".claude/skills/a/x.py" in q and "Bash(ls -la)" in q for q in log["review"]["questions"])
         else [f"refused edit or command not reported: {log['review']['questions']}"])

    def checks_with_env(work, origin, log, err, calls, claude_called):
        prompt = (Path(work).parent / "claude.log.prompt").read_text(encoding="utf-8")
        return [] if "CI=1 " in prompt else ["the review prompt lists the checks without the env the pipeline runs them with"]
    case("review prompt names the checks with their env", cfg={"check_env": {"CI": "1"}}, want_ok=True, check=checks_with_env)
    case("no JSON line becomes a question", want_ok=False, reason="question", FAKE_REVIEW="nojson")
    case("one-way door needs a person", want_ok=False, reason="door is one-way", FAKE_DOOR="one-way")

    def judged_three_times_no_shell(work, origin, log, err, calls, claude_called):
        doors = [p.read_text(encoding="utf-8") + " " for p in Path(work).parent.glob("claude.log.door-*") if p.name != "claude.log.door-yes"]
        out = [] if len(doors) == 3 else [f"door judged {len(doors)} times, want 3"]
        if any("--disallowedTools Bash " not in l or "--permission-mode default" not in l for l in doors):
            out.append("a door judge can use a shell")
        if log["door"]["door"] != "two-way" or log["body"]["door"] != "two-way":
            out.append(f"all-no judges should give two-way: {log['door']}")
        return out
    case("door is judged three times by judges without a shell", want_ok=True, check=judged_three_times_no_shell)
    case("one judge of three saying yes makes the door one-way", want_ok=False, reason="door is one-way", FAKE_DOOR="split",
         check=lambda w, o, log, *a: [] if log["door"]["votes"]["outbound"] == 1 and "1/3" in log["door"]["reason"] else [f"votes not kept: {log['door']}"])
    case("judges with no usable answer make the door one-way", want_ok=False, reason="door is one-way", FAKE_DOOR="garbage",
         check=lambda w, o, log, *a: [] if log["door"]["missing"] == 3 else [f"missing answers not counted: {log['door']}"])

    def body_door_replaced(work, origin, log, err, calls, claude_called):
        body = (Path(git(work, "rev-parse", "--absolute-git-dir")) / "pr-pipeline" / "feat_x.md").read_text(encoding="utf-8")
        out = [] if body.count("## Merge Danger") == 1 and "**Door:** one-way" in body else [f"body Merge Danger not replaced: {body[-300:]}"]
        return out + ([] if log["body"]["door"] == "one-way" else ["body check did not read the judged door"])
    case("the agent's own Door in the body is replaced by the judged one", want_ok=False, reason="door is one-way",
         FAKE_DOOR="one-way", check=body_door_replaced)
    case("failing checks stop before review", files={"FAIL": "x\n"}, want_code=1, check=no_review_call)
    case("protected path needs a person", files={".github/workflows/ci.yml": "on: push\n"}, want_ok=False, reason="protected")
    case("too many lines needs a person", cfg={"max_changed_lines": 1}, want_ok=False, reason="changed lines")
    case("CI failure needs a person", want_ok=False, reason="CI is failure", FAKE_CI='[{"bucket": "fail"}]')
    case("no CI at all is fine", want_ok=True, FAKE_CI="[]")
    case("migration path is a one-way signal", files={"migrations/001.sql": "create table t(x int);\n"},
         want_ok=False, reason="one-way signals")

    with tempfile.TemporaryDirectory() as d:
        std = Path(d) / "std.md"
        std.write_text("```one-way\nsecret | * | content | (?i)secret-project | block\n```\n", encoding="utf-8")
        case("user block rule needs a person", files={"app.py": "# secret-project notes\n"}, want_ok=False,
             reason="blocked by your one-way rules", REVIEW_STANDARDS=str(std))

    with tempfile.TemporaryDirectory() as d:
        work, _ = make_repo(d)
        git(work, "switch", "-q", "main")
        code, _, err, _, _ = pipeline(work, d)
        if code != 2:
            failed.append(f"running on the base branch must be exit 2, got {code} {err}")

    base = {"ok": True, "problems": [], "door": "two-way", "one_way_signals": []}
    cfg = {**pp.DEFAULTS, "protected_paths": ["scripts/hooks/"]}
    ok, why = pp.decide(cfg, checks_ok=True, ci="success", body_report=base, questions=[], user_blocks=[], changed_lines=10, paths=["a.py"])
    if not ok or why:
        failed.append(f"decide: clean change should pass, got {why}")
    ok, why = pp.decide(cfg, checks_ok=False, ci="pending", body_report={**base, "door": None, "ok": False, "problems": ["x"]},
                        questions=["q"], user_blocks=["b"], changed_lines=999, paths=["scripts/hooks/g.py"])
    if ok or len(why) != 8:
        failed.append(f"decide: every unmet condition should be listed (8), got {len(why)}: {why}")

    for f in failed:
        print("FAIL", f)
    print("ok" if not failed else f"{len(failed)} failed")
    sys.exit(1 if failed else 0)
