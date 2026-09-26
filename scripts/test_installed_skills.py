"""Self-test for installed_skills.py. Run: python scripts/test_installed_skills.py"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("installed_skills", HERE / "installed_skills.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failed = []
total = 0


def check(label, ok, detail=""):
    global total
    total += 1
    if not ok:
        failed.append(f"{label} {detail}")


def write(path, text, newline="\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


with tempfile.TemporaryDirectory() as tmp:
    repo, home = Path(tmp) / "repo", Path(tmp) / "home"
    write(repo / "alpha" / "SKILL.md", "---\nname: alpha\n---\nbody\n")
    write(repo / "alpha" / "scripts" / "tool.py", "print(1)\n")
    write(repo / "beta" / "SKILL.md", "---\nname: beta\n---\nbody\n")
    write(home / "alpha" / "SKILL.md", "---\nname: alpha\n---\nbody\n", newline="\r\n")
    write(home / "alpha" / "scripts" / "tool.py", "print(1)\n")
    write(home / "alpha" / "scripts" / "__pycache__" / "tool.pyc", "cache")

    problems, stale = mod.compare(repo, home)
    check("line endings and __pycache__ are not differences", not any("alpha" in p for p in problems), str(problems))
    check("missing skill flagged", any(p.startswith("beta: not installed") for p in problems), str(problems))
    check("only beta needs a sync", stale == {"beta"}, str(stale))

    write(home / "alpha" / "scripts" / "tool.py", "print(2)\n")
    problems, stale = mod.compare(repo, home)
    check("changed file flagged", any("scripts/tool.py differs" in p for p in problems), str(problems))

    write(home / "alpha" / "extra.md", "only installed\n")
    problems, stale = mod.compare(repo, home)
    check("extra installed file reported", any("extra.md exists only" in p for p in problems), str(problems))

    r = subprocess.run([sys.executable, str(HERE / "installed_skills.py"), "--repo-skills", str(repo), "--install-dir", str(home)], capture_output=True, text=True, encoding="utf-8")
    check("exit 1 and names the fix command", r.returncode == 1 and "installed_skills.py --sync" in r.stdout, r.stdout)

    r = subprocess.run([sys.executable, str(HERE / "installed_skills.py"), "--sync", "--repo-skills", str(repo), "--install-dir", str(home)], capture_output=True, text=True, encoding="utf-8")
    check("--sync brings everything level and exits 0", r.returncode == 0, r.stdout)
    check("synced file content", (home / "alpha" / "scripts" / "tool.py").read_text(encoding="utf-8") == "print(1)\n")
    check("extra installed file survives --sync", (home / "alpha" / "extra.md").exists())

for f in failed:
    print("FAIL", f)
print(f"{total - len(failed)}/{total} passed" if not failed else f"{len(failed)} failed")
sys.exit(1 if failed else 0)
