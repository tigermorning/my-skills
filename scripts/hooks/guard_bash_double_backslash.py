"""PreToolUse hook: deny Bash commands that contain two backslashes in a row.

Why: in this environment the Bash tool turns every `\\` into a single `\` before the
shell runs, even inside single quotes and quoted heredocs (`<<'EOF'`). A Python or JS
snippet written with `\\r` then receives `\r` and writes a real carriage return, or a
regex loses its escape. Nothing fails at once; the damage shows up later in the file.
PowerShell keeps both backslashes, so only Bash is checked.

Input: hook JSON on stdin. Output: a deny decision on stdout, or nothing.
"""
import json
import sys

DOUBLE = "\\" * 2


def decide(payload):
    if payload.get("tool_name") != "Bash":
        return None
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if DOUBLE not in cmd:
        return None
    return (
        "Bash 명령에 역슬래시 두 개(\\\\)가 있습니다. 이 환경의 Bash 도구는 셸에 넘기기 전에 이것을 하나로 줄입니다"
        "(작은따옴표·<<'EOF' 안도 마찬가지). 스크립트·정규식·경로에 역슬래시가 필요하면 "
        "Write 도구로 파일을 쓴 뒤 그 파일을 실행하세요(파이썬 안에서는 chr(92)). "
        "한 줄짜리면 PowerShell 도구를 쓰고, 경로는 슬래시(/)로 쓰세요. skill: safe-script-patching"
    )


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
