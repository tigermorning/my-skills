"""Tests for guard_recursive_delete.py against real directories. Run: python test_recursive_delete.py

The guard allows anything under the temp dir, so the sandbox repo lives under the
home directory and is removed at the end.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def deny(cmd, tool="Bash"):
    r = subprocess.run([sys.executable, str(HERE / "guard_recursive_delete.py")], input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}}).encode("utf-8"), capture_output=True)
    out = r.stdout.decode("utf-8").strip()
    return bool(out) and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


if __name__ == "__main__":
    box = Path(tempfile.mkdtemp(prefix="guard-rm-test-", dir=Path.home()))
    try:
        repo = box / "repo"
        (repo / "tracked").mkdir(parents=True)
        (repo / "tracked" / "a.txt").write_text("a", encoding="utf-8")
        (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        git("init", "-q", cwd=repo)
        git("-c", "user.email=t@t", "-c", "user.name=t", "add", ".", cwd=repo)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init", cwd=repo)
        (repo / "fresh").mkdir()
        (repo / "fresh" / "new.txt").write_text("new", encoding="utf-8")
        (repo / "__pycache__").mkdir()
        (repo / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")
        outside = box / "notes"
        outside.mkdir()
        (outside / "n.txt").write_text("n", encoding="utf-8")
        tmp = Path(tempfile.mkdtemp())
        p = lambda x: str(x).replace("\\", "/")

        cases = [
            ("untracked dir in repo", f'rm -rf "{p(repo / "fresh")}"', True),
            ("tracked clean dir", f"rm -rf {p(repo / 'tracked')}", False),
            ("ignored cache dir", f"rm -rf {p(repo / '__pycache__')}", False),
            ("temp dir", f"rm -rf {p(tmp)}", False),
            ("non-repo dir outside temp", f"rm -r {p(outside)}", True),
            ("Git Bash /c/ path to untracked dir", "rm -rf /" + p(repo / "fresh").replace(":", "", 1), True),
            ("non-recursive rm", f"rm -f {p(outside / 'n.txt')}", False),
            ("heredoc text only", f"cat > m.txt <<'EOF'\nrm -rf {p(outside)}\nEOF", False),
            ("relative path after cd", f"cd {p(box)} && rm -rf notes", True),
            ("relative path after cd into temp", f"cd {p(tmp)} && rm -rf notes", False),
            ("PowerShell Remove-Item -Recurse", f'Remove-Item -Recurse -Force "{p(outside)}"', True),
        ]
        failed = 0
        for label, cmd, want in cases:
            if want is None:
                continue  # relative path after cd depends on the hook's cwd; not asserted
            tool = "PowerShell" if cmd.startswith("Remove-Item") else "Bash"
            got = deny(cmd, tool)
            if got != want:
                failed += 1
                print(f"FAIL {label}: want deny={want} got={got}")
        n = sum(1 for c in cases if c[2] is not None)
        print(f"{n - failed}/{n} passed")
        shutil.rmtree(tmp, ignore_errors=True)
    finally:
        shutil.rmtree(box, ignore_errors=True)
    sys.exit(1 if failed else 0)
