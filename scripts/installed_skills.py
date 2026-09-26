"""Compare the repo's skills with the user-wide copies Claude Code actually loads.

Usage:
    python scripts/installed_skills.py            # report differences, exit 1 if any
    python scripts/installed_skills.py --sync     # copy repo skills over the installed ones

A skill is only found when it sits directly at ~/.claude/skills/<name>/SKILL.md. The installed
copy is a plain copy, so editing the repo without copying leaves the old text loaded in every
other project. CI cannot see the home directory, so this runs locally (check_skills.py calls it
when the install directory exists and CI is not set).

Files are compared with line endings normalised, so a CRLF checkout does not count as a
difference. Files that exist only in the installed copy are reported but never deleted.
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"
DEFAULT_INSTALL = Path.home() / ".claude" / "skills"
SKIP_PARTS = {"__pycache__"}


def files_of(base):
    return {p.relative_to(base).as_posix(): p for p in base.rglob("*") if p.is_file() and not SKIP_PARTS & set(p.parts) and p.suffix != ".pyc"}


def normalised(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def compare(repo_skills, install_dir):
    """Return (problems, fixable_names): one line per difference, in a stable order."""
    problems, stale = [], set()
    for skill in sorted(p for p in Path(repo_skills).iterdir() if p.is_dir()):
        target = Path(install_dir) / skill.name
        if not (target / "SKILL.md").exists():
            problems.append(f"{skill.name}: not installed at {target} (a skill nested deeper is not discovered)")
            stale.add(skill.name)
            continue
        repo_files, installed_files = files_of(skill), files_of(target)
        for rel in sorted(repo_files):
            if rel not in installed_files:
                problems.append(f"{skill.name}: {rel} missing from the installed copy")
                stale.add(skill.name)
            elif normalised(repo_files[rel]) != normalised(installed_files[rel]):
                problems.append(f"{skill.name}: {rel} differs from the installed copy")
                stale.add(skill.name)
        for rel in sorted(set(installed_files) - set(repo_files)):
            problems.append(f"{skill.name}: {rel} exists only in the installed copy (not deleted by --sync)")
    return problems, stale


def sync(repo_skills, install_dir, names):
    for name in sorted(names):
        source, target = Path(repo_skills) / name, Path(install_dir) / name
        for rel, path in files_of(source).items():
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true", help="copy repo skills over stale or missing installed ones")
    ap.add_argument("--repo-skills", default=str(SKILLS))
    ap.add_argument("--install-dir", default=str(DEFAULT_INSTALL))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    problems, stale = compare(a.repo_skills, a.install_dir)
    if a.sync and stale:
        sync(a.repo_skills, a.install_dir, stale)
        print(f"synced {len(stale)} skill(s): {', '.join(sorted(stale))}")
        problems, stale = compare(a.repo_skills, a.install_dir)
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    if stale:
        print("fix: python scripts/installed_skills.py --sync")
    sys.exit(1 if stale else 0)


if __name__ == "__main__":
    main()
