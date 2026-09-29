"""cleanup_merged_branch.py must delete a merged remote branch, refuse an unmerged one, and verify.

Run: python scripts/test_cleanup_merged_branch.py
Builds a throwaway bare remote and clone under the temp dir; touches no real repository.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "cleanup_merged_branch.py"
failed, total = [], 0


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def run(clone, *args):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=clone, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def check(label, ok, detail=""):
    global total
    total += 1
    if not ok:
        failed.append(f"{label}: {detail[-300:]}")


def remote_has(clone, branch):
    return bool(git("ls-remote", "--heads", "origin", branch, cwd=clone))


with tempfile.TemporaryDirectory() as tmp:
    remote, clone = Path(tmp) / "remote.git", Path(tmp) / "clone"
    git("init", "-q", "--bare", "-b", "master", str(remote), cwd=tmp)
    git("clone", "-q", str(remote), str(clone), cwd=tmp)
    for k, v in (("user.email", "t@example.com"), ("user.name", "t")):
        git("config", k, v, cwd=clone)
    (clone / "a.txt").write_text("a\n", encoding="utf-8")
    git("add", ".", cwd=clone)
    git("commit", "-q", "-m", "base", cwd=clone)
    git("push", "-q", "-u", "origin", "master", cwd=clone)

    # merged: branch commit reaches master through a merge commit, the way `gh pr merge --merge` does
    git("switch", "-q", "-c", "feat/done", cwd=clone)
    (clone / "b.txt").write_text("b\n", encoding="utf-8")
    git("add", ".", cwd=clone)
    git("commit", "-q", "-m", "done", cwd=clone)
    git("push", "-q", "-u", "origin", "feat/done", cwd=clone)
    git("switch", "-q", "master", cwd=clone)
    git("merge", "-q", "--no-ff", "-m", "merge", "feat/done", cwd=clone)
    git("push", "-q", "origin", "master", cwd=clone)

    # unmerged: pushed but never merged
    git("switch", "-q", "-c", "feat/open", cwd=clone)
    (clone / "c.txt").write_text("c\n", encoding="utf-8")
    git("add", ".", cwd=clone)
    git("commit", "-q", "-m", "open", cwd=clone)
    git("push", "-q", "-u", "origin", "feat/open", cwd=clone)
    git("switch", "-q", "master", cwd=clone)

    code, out = run(clone, "feat/open")
    check("unmerged branch refused", code == 1 and remote_has(clone, "feat/open"), out)
    check("refusal names the alternative", "gh pr view" in out or "머지" in out, out)

    code, out = run(clone, "feat/done")
    check("merged branch deleted on the remote", code == 0 and not remote_has(clone, "feat/done"), out)
    check("merged local branch deleted", not git("branch", "--list", "feat/done", cwd=clone), out)

    code, out = run(clone, "feat/done")
    check("already deleted is not an error", code == 0 and "없" in out, out)

    code, out = run(clone, "master")
    check("base branch is never deleted", code == 1 and remote_has(clone, "master"), out)

for f in failed:
    print("FAIL", f)
print(f"{total - len(failed)}/{total} passed" if not failed else f"{len(failed)} failed")
sys.exit(1 if failed else 0)
