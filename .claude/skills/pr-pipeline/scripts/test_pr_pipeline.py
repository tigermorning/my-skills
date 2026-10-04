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
import json, os, re, subprocess, sys
prompt = sys.stdin.read()
open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8").write("called\n")
body_path = re.search(r"BODY_PATH: (.+)", prompt).group(1).strip()
mode = os.environ.get("FAKE_REVIEW", "clean")
open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8").write(" ".join(sys.argv[1:]) + "\n")
if mode == "autherror":
    print(json.dumps({"type": "result", "is_error": True, "result": "Failed to authenticate: OAuth session expired"}))
    sys.exit(1)
def commit(path, text, msg):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)
    subprocess.run(["git", "add", path], check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], check=True)
questions, fixed = [], []
if mode == "fix":
    commit("app.py", "# reason: keeps the helper small\n", "review: tidy helper"); fixed.append("review: tidy helper")
if mode == "break":
    commit("FAIL", "x\n", "review: oops"); fixed.append("review: oops")
if mode == "outside":
    commit("other.py", "x = 1\n", "review: touch other"); fixed.append("review: touch other")
if mode == "foreign":
    commit("app.py", "# session log\n", "project-session-memory: capture session x")
if mode == "dirty":
    open("app.py", "a", encoding="utf-8").write("# left behind\n")
if mode == "question":
    questions.append("is the helper meant to be public?")
body = os.environ.get("FAKE_BODY") or GOOD
if mode != "nobody":
    open(body_path, "w", encoding="utf-8").write(body)
answer = {"title": "Add helper", "questions": questions, "fixed": fixed}
if mode == "nojson":
    print(json.dumps({"type": "result", "result": "done, no json line"}))
else:
    print(json.dumps({"type": "result", "result": "done\n" + json.dumps(answer)}))
'''.replace("GOOD", repr(GOOD_BODY), 1).replace("GOOD\n", repr(GOOD_BODY) + "\n")

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
    (work / "check.py").write_text("import os, sys\nsys.exit(1 if os.path.exists('FAIL') else 0)\n", encoding="utf-8")
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

    def case(name, cfg=None, files=None, args=(), want_code=0, want_ok=None, reason=None, check=None, **env):
        with tempfile.TemporaryDirectory() as d:
            work, origin = make_repo(d, cfg, files)
            code, log, err, calls, claude_called = pipeline(work, d, args, **env)
            problems = []
            if code != want_code:
                problems.append(f"exit {code} != {want_code} ({err.strip()[:200]})")
            if log and want_ok is not None and log["auto_merge_ok"] != want_ok:
                problems.append(f"auto_merge_ok {log['auto_merge_ok']} != {want_ok}: {log['reasons']}")
            if log and reason and not any(reason in x for x in log["reasons"]):
                problems.append(f"no reason containing {reason!r}: {log['reasons']}")
            if check:
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
        if (Path(work) / "FAIL").exists():
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
    case("review fix commit is fine", want_ok=True, FAKE_REVIEW="fix",
         check=lambda w, o, log, *a: [] if len(log["review"]["commits"]) == 1 else ["fix commit not recorded"])
    case("review fix that breaks checks is reverted", want_ok=False, FAKE_REVIEW="break", check=reverted)
    case("review touching other files becomes a question", want_ok=False, reason="question", FAKE_REVIEW="outside")
    case("review leaving a dirty tree stops", want_code=1, FAKE_REVIEW="dirty")
    case("a non-review commit during review becomes a question", want_ok=False, reason="question", FAKE_REVIEW="foreign",
         check=lambda w, o, log, *a: [] if any("not a review fix" in q for q in log["review"]["questions"]) else ["foreign commit not flagged"])
    case("expired login stops with the agent's own message", want_code=1, FAKE_REVIEW="autherror",
         check=lambda w, o, log, err, *a: [] if "OAuth session expired" in err and "/login" in err else [f"message lost: {err[:200]}"])

    def user_settings_only(work, origin, log, err, calls, claude_called):
        args = (Path(work).parent / "claude.log").read_text(encoding="utf-8")
        return [] if "--setting-sources user" in args else ["review agent not limited to user settings (repo hooks would run)"]
    case("review agent runs with user settings only", want_ok=True, check=user_settings_only)
    case("no body stops", want_code=1, FAKE_REVIEW="nobody")
    case("no JSON line becomes a question", want_ok=False, reason="question", FAKE_REVIEW="nojson")
    case("one-way door needs a person", want_ok=False, reason="door is one-way",
         FAKE_BODY=GOOD_BODY.replace("**Door:** two-way", "**Door:** one-way"))
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
