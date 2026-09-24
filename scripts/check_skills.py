"""Hard checks for this repo's skills. Runs in CI and locally: python scripts/check_skills.py

Each check turns a rule that used to live only in review comments into a failure:
- SKILL.md frontmatter: name matches the directory, description present and <= 1024 chars
- [[wiki-links]] in skill bodies point at a skill that exists in this repo
- evals.json: well-formed, assertion ids unique, check type known, every eval with
  "script" checks has a grader in scripts/skill-evals/grade.py
- graders discriminate: running them on the untouched fixtures must fail at least one
  script check (a grader that passes broken code proves nothing)
- hook guards pass their table tests
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"
CHECK_TYPES = {"script", "transcript", "judge"}
FIXTURE_OF = {  # eval name -> fixture dir (relative to the skill's evals/fixtures)
    "curl-create-korean-note": "notes-api",
    "misdiagnosed-parse-error": "notes-api",
    "phone-normalizer-real-csv": "phone-cleanup",
    "sentence-splitter-real-news": "sentence-split",
}
# On the untouched fixture these evals' outcome checks must fail; the misdiagnosis eval
# is excluded because an untouched server.py is exactly the passing state there.
MUST_FAIL_ON_FIXTURE = {"curl-create-korean-note", "phone-normalizer-real-csv", "sentence-splitter-real-news"}

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
    path = skill_dir / "evals" / "evals.json"
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
    fixture = skill_dir / "evals" / "fixtures" / FIXTURE_OF[name]
    with tempfile.TemporaryDirectory() as tmp:
        job = Path(tmp) / "job"
        shutil.copytree(fixture, job)
        try:
            result = grade.GRADERS[name](job, [])
        except Exception as e:  # noqa: BLE001 — surface the crash as a check failure
            return err(rel, f"grader for '{name}' crashed on the fixture: {e}")
    if all(r["passed"] for r in result):
        err(rel, f"grader for '{name}' passes the untouched fixture, so it cannot catch a broken run")


def check_self_tests():
    """Run every test script that guards a tool: hook guards and skill-bundled checkers."""
    tests = [ROOT / "scripts/hooks/test_hooks.py", *sorted(SKILLS.glob("*/scripts/test_*.py"))]
    for t in tests:
        r = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            err(t.relative_to(ROOT), r.stdout.strip() or r.stderr.strip())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dirs = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    names = {p.name for p in dirs}
    grade = load_graders()
    for d in dirs:
        check_skill_md(d, names)
        check_evals(d, grade)
    check_self_tests()
    if errors:
        print("\n".join(f"FAIL {e}" for e in errors))
        print(f"{len(errors)} problem(s)")
        sys.exit(1)
    print(f"ok: {len(dirs)} skills checked")


if __name__ == "__main__":
    main()
