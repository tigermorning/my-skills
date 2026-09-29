"""Delete a PR branch after its merge, only when the merge really contains it, and verify.

Usage: python scripts/cleanup_merged_branch.py <branch> [--base master] [--remote origin]

Why: `gh pr merge --delete-branch` can report success and still leave the remote branch in
place. This checks what is actually on the remote instead of trusting that flag.

- remote branch gone already: says so, exit 0
- remote tip not contained in <remote>/<base>: refuses to delete, exit 1
- otherwise deletes the remote branch, re-reads the remote to confirm, and deletes the
  local branch with `git branch -d` (which itself refuses unmerged work)
"""
import argparse
import subprocess
import sys

PROTECTED = {"master", "main", "develop"}


def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r


def remote_tip(remote, branch):
    out = git("ls-remote", "--heads", remote, branch).stdout.split()
    return out[0] if out else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("branch")
    ap.add_argument("--base", default="master")
    ap.add_argument("--remote", default="origin")
    a = ap.parse_args()

    if a.branch in PROTECTED or a.branch == a.base:
        print(f"'{a.branch}'는 기준 브랜치라 지우지 않습니다. PR 브랜치 이름을 주세요.")
        return 1
    git("fetch", "-q", a.remote)
    tip = remote_tip(a.remote, a.branch)
    if tip is None:
        print(f"원격 브랜치 {a.remote}/{a.branch}가 이미 없습니다.")
    elif git("merge-base", "--is-ancestor", tip, f"{a.remote}/{a.base}", check=False).returncode != 0:
        print(f"{a.remote}/{a.branch}({tip[:7]})가 {a.remote}/{a.base}에 들어 있지 않아 지우지 않습니다.\n"
              f"머지됐는지 `gh pr view <번호> --json state,mergeCommit`로 먼저 확인하세요. "
              f"스쿼시 머지였다면 커밋이 달라 여기서 확인할 수 없으니, 머지 상태를 본 뒤 직접 `git push {a.remote} --delete {a.branch}`로 지웁니다.")
        return 1
    else:
        git("push", "-q", a.remote, "--delete", a.branch)
        left = remote_tip(a.remote, a.branch)
        if left:
            print(f"삭제 명령 뒤에도 {a.remote}/{a.branch}가 남아 있습니다 ({left[:7]}). 권한이나 브랜치 보호 규칙을 확인하세요.")
            return 1
        print(f"원격 브랜치 {a.remote}/{a.branch}({tip[:7]})를 지웠습니다. {a.remote}/{a.base}에 들어 있는 것을 확인함.")
    if git("branch", "--list", a.branch).stdout.strip():
        r = git("branch", "-d", a.branch, check=False)
        print(f"로컬 브랜치 {a.branch}: " + ("지움" if r.returncode == 0 else f"남김 — {(r.stderr or r.stdout).strip()}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
