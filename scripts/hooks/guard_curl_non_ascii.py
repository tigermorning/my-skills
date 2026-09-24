"""PreToolUse hook: deny curl commands whose arguments carry non-ASCII text.

Why: on Windows + Git Bash, /mingw64/bin/curl sends `-d '한글'` as cp949 bytes, not
UTF-8 (reproduced 2026-09-24). The server then rejects the body and the failure
looks like a server bug. Writing the body to a file and sending it with
`--data-binary @file` avoids it. See .claude/skills/non-ascii-via-file.

Input: hook JSON on stdin. Output: a deny decision on stdout, or nothing.
"""
import json
import re
import sys

CURL = re.compile(r"(^|[\s;&|(`])curl(\.exe)?(\s|$)")
NON_ASCII = re.compile(r"[^\x00-\x7f]")


def decide(payload):
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return None
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not CURL.search(cmd) or not NON_ASCII.search(cmd):
        return None
    return (
        "curl 명령에 비ASCII 문자(한글 등)가 인자로 들어 있습니다. 이 환경의 curl은 이런 인자를 "
        "UTF-8이 아닌 cp949로 보냅니다. 본문을 Write 도구로 UTF-8 파일에 쓴 뒤 "
        "`curl --data-binary @파일` 로 보내세요 (URL의 한글은 퍼센트 인코딩). "
        "skill: non-ascii-via-file"
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
