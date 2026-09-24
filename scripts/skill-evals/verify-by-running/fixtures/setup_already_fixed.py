"""Build the 'already fixed' eval repo: commit 1 has the empty-input crash, commit 2 fixes it.

Usage: python setup_already_fixed.py <empty target dir>
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX_OLD = "    return sum(nums) / len(nums)\n"
FIX_NEW = "    if not nums:\n        return None\n    return sum(nums) / len(nums)\n"


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


if __name__ == "__main__":
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)
    for name in ("app.py", "test_app.py"):
        shutil.copy(HERE / "stats-api" / name, target / name)
    git("init", "-q", cwd=target)
    git("config", "user.email", "dev@example.com", cwd=target)
    git("config", "user.name", "dev", cwd=target)
    git("add", ".", cwd=target)
    git("commit", "-q", "-m", "stats: add mean endpoint", cwd=target)
    app = target / "app.py"
    app.write_text(app.read_text(encoding="utf-8").replace(FIX_OLD, FIX_NEW), encoding="utf-8")
    git("commit", "-q", "-am", "stats: return null mean for empty input", cwd=target)
    print(subprocess.run(["git", "log", "--oneline"], cwd=target, capture_output=True, text=True).stdout.strip())
