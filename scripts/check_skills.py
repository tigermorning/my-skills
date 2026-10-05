"""Hard checks for this repo's skills. Runs in CI and locally: python scripts/check_skills.py

Each check turns a rule that used to live only in review comments into a failure:
- SKILL.md frontmatter: name matches the directory, description present and <= 1024 chars
- [[wiki-links]] in skill bodies point at a skill that exists in this repo
- evals.json: well-formed, assertion ids unique, check type known, every eval with
  "script" checks has a grader in scripts/skill-evals/grade.py
- graders discriminate: running them on the untouched fixtures must fail at least one
  script check (a grader that passes broken code proves nothing)
- hook guards pass their table tests
- a skill with evals (scripts/skill-evals/<skill>/evals.json) has last_run.json there
  whose skill_sha256 matches the current SKILL.md, so a skill edit without a fresh
  eval run fails. Evals live outside the skill dir so agents reading a skill cannot
  find the tasks and fixtures it is graded on
- code comments in scripts carry the reason, not history: no dates and no
  who-said-it provenance (agents tend to write irrelevant history as comments)
- the user-wide copies in ~/.claude/skills match the repo (local only, skipped when CI is
  set or the directory is missing; fix with scripts/installed_skills.py --sync)
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"
EVALS = ROOT / "scripts" / "skill-evals"
CHECK_TYPES = {"script", "transcript", "judge"}
FIXTURE_OF = {  # eval name -> fixture dir (relative to scripts/skill-evals/<skill>/fixtures)
    "curl-create-korean-note": "notes-api",
    "misdiagnosed-parse-error": "notes-api",
    "phone-normalizer-real-csv": "phone-cleanup",
    "sentence-splitter-real-news": "sentence-split",
    "new-project-gate": "blank",
    "guardrails-before-first-feature": "notes-cli",
    "map-new-ui-app": "memo-board",
}
# On the untouched fixture these evals' outcome checks must fail; the misdiagnosis eval
# is excluded because an untouched server.py is exactly the passing state there.
MUST_FAIL_ON_FIXTURE = {"curl-create-korean-note", "phone-normalizer-real-csv", "sentence-splitter-real-news",
                     "new-project-gate", "guardrails-before-first-feature", "map-new-ui-app"}

errors = []


def err(where, msg):
    errors.append(f"{where}: {msg}")


def frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            fields[k.strip()] = v.strip()
    return fields


def check_skill_md(skill_dir, names):
    path = skill_dir / "SKILL.md"
    rel = path.relative_to(ROOT)
    if not path.exists():
        return err(rel, "missing SKILL.md")
    text = path.read_text(encoding="utf-8")
    fm = frontmatter(text)
    if fm is None:
        return err(rel, "no YAML frontmatter")
    if fm.get("name") != skill_dir.name:
        err(rel, f"frontmatter name '{fm.get('name')}' != directory '{skill_dir.name}'")
    desc = fm.get("description", "")
    if not desc:
        err(rel, "empty description")
    elif len(desc) > 1024:
        err(rel, f"description is {len(desc)} chars (max 1024)")
    for link in re.findall(r"\[\[([^\]]+)\]\]", text):
        if link not in names:
            err(rel, f"[[{link}]] does not match any skill in .claude/skills")


def load_graders():
    spec = importlib.util.spec_from_file_location("grade", ROOT / "scripts/skill-evals/grade.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_evals(skill_dir, grade):
    path = EVALS / skill_dir.name / "evals.json"
    if not path.exists():
        return
    rel = path.relative_to(ROOT)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return err(rel, f"invalid JSON: {e}")
    if data.get("skill_name") != skill_dir.name:
        err(rel, f"skill_name '{data.get('skill_name')}' != directory '{skill_dir.name}'")
    for ev in data.get("evals", []):
        name = ev.get("name", "?")
        for key in ("id", "name", "prompt", "assertions"):
            if key not in ev:
                err(rel, f"eval '{name}' missing '{key}'")
        ids = [a.get("id") for a in ev.get("assertions", [])]
        if len(ids) != len(set(ids)):
            err(rel, f"eval '{name}' has duplicate assertion ids")
        for a in ev.get("assertions", []):
            if a.get("check") not in CHECK_TYPES:
                err(rel, f"eval '{name}' assertion '{a.get('id')}' has check '{a.get('check')}'")
        if any(a.get("check") == "script" for a in ev.get("assertions", [])) and name not in grade.GRADERS:
            err(rel, f"eval '{name}' has script checks but no grader in grade.py")
        if name in MUST_FAIL_ON_FIXTURE:
            check_discriminates(skill_dir, name, grade, rel)


def check_discriminates(skill_dir, name, grade, rel):
    fixture = EVALS / skill_dir.name / "fixtures" / FIXTURE_OF[name]
    with tempfile.TemporaryDirectory() as tmp:
        job = Path(tmp) / "job"
        shutil.copytree(fixture, job)
        try:
            result = grade.GRADERS[name](job, [])
        except Exception as e:  # noqa: BLE001 — surface the crash as a check failure
            return err(rel, f"grader for '{name}' crashed on the fixture: {e}")
    if all(r["passed"] for r in result):
        err(rel, f"grader for '{name}' passes the untouched fixture, so it cannot catch a broken run")


def check_eval_freshness(skill_dir):
    evals = EVALS / skill_dir.name
    if not (evals / "evals.json").exists():
        return
    rel = (evals / "last_run.json").relative_to(ROOT)
    current = hashlib.sha256((skill_dir / "SKILL.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    try:
        recorded = json.loads((evals / "last_run.json").read_text(encoding="utf-8")).get("skill_sha256")
    except FileNotFoundError:
        return err(rel, "missing: run the evals and record the result")
    if recorded != current:
        err(rel, "SKILL.md changed since the last eval run; rerun the evals and update last_run.json "
                 f"(python scripts/skill-evals/record_run.py {skill_dir.name} ...)")


HISTORY = re.compile(r"\b20\d\d-\d\d-\d\d\b|\buser said\b|사용자가 말|님이 말", re.I)


def check_comment_hygiene():
    for path in [*ROOT.glob("scripts/**/*.py"), *SKILLS.glob("*/scripts/**/*.py")]:
        if "__pycache__" in path.parts:
            continue
        in_doc = False
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            quotes = line.count('"""') + line.count("'''")
            is_comment = in_doc or line.lstrip().startswith("#") or quotes
            if quotes % 2:
                in_doc = not in_doc
            if is_comment and HISTORY.search(line):
                err(f"{path.relative_to(ROOT)}:{n}", "comment records history (date or who said it); keep only the reason")


def check_self_tests():
    """Run every test script that guards a tool: hook guards and skill-bundled checkers.
    Returns the scripts that passed, so a reader of a green run can see what it covered."""
    passed = []
    tests = [*sorted(ROOT.glob("scripts/test_*.py")), *sorted(ROOT.glob("scripts/hooks/test_*.py")), *sorted(ROOT.glob("scripts/skill-evals/test_*.py")), *sorted(SKILLS.glob("*/scripts/test_*.py"))]
    for t in tests:
        r = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            err(t.relative_to(ROOT), r.stdout.strip() or r.stderr.strip())
        else:
            passed.append(t.relative_to(ROOT).as_posix())
    return passed


def check_installed_copies():
    """The user-wide copies are what other projects load, so a stale one is a failure locally.

    CI has no home directory to compare, so it is skipped there and when nothing is installed.
    """
    install = Path.home() / ".claude" / "skills"
    if os.environ.get("CI") or not install.is_dir():
        return
    spec = importlib.util.spec_from_file_location("installed_skills", ROOT / "scripts" / "installed_skills.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    problems, stale = mod.compare(SKILLS, install)
    for p in problems:
        if p.split(": ", 1)[0] in stale:
            err("installed copy", f"{p}; fix: python scripts/installed_skills.py --sync")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dirs =sorted(p for p in SKILLS.iterdir() if p.is_dir())
    names = {p.name for p in dirs}
    grade = load_graders()
    for d in dirs:
        check_skill_md(d, names)
        check_evals(d, grade)
        check_eval_freshness(d)
    check_comment_hygiene()
    passed = check_self_tests()
    check_installed_copies()
    if errors:
        print("\n".join(f"FAIL {e}" for e in errors))
        print(f"{len(errors)} problem(s)")
        sys.exit(1)
    for t in passed:
        print(f"self-test ok: {t}")
    print(f"ok: {len(dirs)} skills checked, {len(passed)} self-tests passed")


if __name__ == "__main__":
    main()
