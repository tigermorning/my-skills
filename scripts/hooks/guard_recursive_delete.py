"""PreToolUse hook: deny recursive deletes of files that nothing can bring back.

Why: `rm -rf <dir>` on a path outside the temp area wipes work that is not in
git yet (new, uncommitted files) or lives outside any repo; neither git nor the
recycle bin can restore it. Recursive deletes stay allowed for:
- anything under the system temp directory (scratch, job folders),
- paths git ignores (build output, caches such as __pycache__, node_modules),
- directories whose every file is tracked by git and unmodified (git restores them).

Input: hook JSON on stdin. Output: a deny decision on stdout, or nothing.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", re.S)
RM = re.compile(r"(?:^|[;&|(]\s*|\bxargs\s+)rm\s+((?:-[\w-]+\s+)+)(.+?)(?=\s*(?:&&|\|\||[;|]|$))", re.M)
PS = re.compile(r"\b(?:Remove-Item|rmdir|rd|del)\b(?=[^;|]*-Recurse|[^;|]*\s/s\b)([^;|]*)", re.I)
TEMP = [Path(tempfile.gettempdir()).resolve()]

REASON = (
    "되돌릴 수 없는 재귀 삭제입니다: {path}. 임시 폴더 밖이고, git에 커밋되지 않은 파일이 있거나 git 밖이라 "
    "지우면 복구할 수 없습니다. 직접 만든 파일만 개별로 지우거나, 먼저 `git status`/`git clean -n`으로 무엇이 "
    "사라지는지 확인하고 사용자에게 물어보세요."
)


def git(args, cwd):
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None


def unrecoverable(path):
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        p = p.resolve()
    except OSError:
        return False
    if not p.exists():
        return False
    if any(p == t or t in p.parents for t in TEMP):
        return False
    base = p if p.is_dir() else p.parent
    top = git(["rev-parse", "--show-toplevel"], base)
    if not top or top.returncode != 0:
        return True  # outside any repo: nothing can restore it
    ignored = git(["check-ignore", "-q", str(p)], base)
    if ignored and ignored.returncode == 0:
        return False
    status = git(["status", "--porcelain", "--untracked-files=all", "--ignored=no", "--", str(p)], base)
    return bool(status and status.stdout.strip())  # untracked or modified content would be lost


CD = re.compile(r"\bcd\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s;&|]+))")


def _cwd_at(cmd, pos):
    """Directory in effect at `pos`: the last `cd <dir>` before it, else the hook's cwd."""
    last = None
    for m in CD.finditer(cmd, 0, pos):
        last = m.group(1) or m.group(2) or m.group(3)
    if not last:
        return None
    return re.sub(r"^/([a-zA-Z])/", r"\1:/", last)


def targets(cmd):
    cmd = HEREDOC.sub("<<heredoc", cmd)
    out = []
    for m in RM.finditer(cmd):
        flags, rest = m.group(1), m.group(2)
        if re.search(r"-\w*[rR]|--recursive", flags):
            try:
                names = [t for t in shlex.split(rest, posix=True) if not t.startswith("-")]
            except ValueError:
                names = rest.split()
            base = _cwd_at(cmd, m.start())
            for t in names:
                t = re.sub(r"^/([a-zA-Z])/", r"\1:/", t)
                out.append(str(Path(base) / t) if base and not Path(t).is_absolute() and not t.startswith("~") else t)
    for rest in PS.findall(cmd):
        m = re.search(r"(?:-(?:Path|LiteralPath)\s+)?[\"']([^\"']+)[\"']|(?:^|\s)([A-Za-z]:[\\/][^\s]+|/[^\s]+)", rest)
        if m:
            out.append(m.group(1) or m.group(2))
    return out


def decide(payload):
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return None
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    for t in targets(cmd):
        t = re.sub(r"^/([a-zA-Z])/", r"\1:/", t)  # Git Bash /c/... -> c:/...
        if "*" in t or "$" in t or "`" in t:
            continue  # cannot resolve globs or variables statically; the path check needs a literal path
        if unrecoverable(t):
            return REASON.format(path=t)
    return None


def main():
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    reason = decide(payload)
    if reason:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}, ensure_ascii=False))


if __name__ == "__main__":
    main()
