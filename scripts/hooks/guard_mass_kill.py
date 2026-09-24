"""PreToolUse hook: deny commands that kill processes by name instead of by PID.

Why: `taskkill /F /IM python.exe`, `pkill python`, `killall node` or
`Get-Process python | Stop-Process` stop every matching process on the machine,
including the user's own servers, jobs and tool processes, not just the one the
agent started. Stop the PID you started, or look up the PID that owns your port.

Input: hook JSON on stdin. Output: a deny decision on stdout, or nothing.
"""
import json
import re
import sys

PATTERNS = [
    re.compile(r"\btaskkill(\.exe)?\b(?=[^|;&]*[/-]{1,2}IM\b)", re.I),
    re.compile(r"\bkillall\b", re.I),
    re.compile(r"\bpkill\b(?![^|;&]*\s-f\s+[\"'][^\"']*\s\d{2,5}[\"'])", re.I),
    re.compile(r"\bStop-Process\b[^|;&]*-(Name|ProcessName)\b", re.I),
    re.compile(r"\bGet-Process\b[^|;]*\|\s*(Stop-Process|kill)\b", re.I),
    re.compile(r"\bwmic\b[^|;&]*\bprocess\b[^|;&]*\bwhere\b[^|;&]*\bname\b[^|;&]*\bdelete\b", re.I),
]

REASON = (
    "프로세스를 이름으로 한꺼번에 죽이는 명령입니다. 컴퓨터 전체의 같은 이름 프로세스"
    "(사용자 서버·작업·도구 포함)가 함께 종료됩니다. 직접 띄운 프로세스의 PID로 종료하세요: "
    "Bash `kill <PID>` / `taskkill //PID <PID> //F`, PowerShell `Stop-Process -Id <PID>`. "
    "포트 주인 PID는 `netstat -ano | grep :<포트>` 또는 "
    "`Get-NetTCPConnection -LocalPort <포트> -State Listen`으로 찾습니다."
)


HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", re.S)


def decide(payload):
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return None
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    cmd = HEREDOC.sub("<<heredoc", cmd)  # heredoc bodies are data (commit messages, files), not commands
    return REASON if any(p.search(cmd) for p in PATTERNS) else None


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
