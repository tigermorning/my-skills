"""PreToolUse hook: deny typing a pinned GitHub URL into a browser form.

Why: the user submits repo URLs for assignments and keeps pushing fixes after
submitting. A URL pinned to a commit, tag or branch (/tree/..., /blob/...,
/commit/..., /releases/tag/...) freezes the submission, and later fixes never
reach the grader (happened 2026-09-17). Only the repo base URL is allowed.

Input: hook JSON on stdin. Output: a deny decision on stdout, or nothing.
"""
import json
import re
import sys

PINNED = re.compile(
    r"github\.com/[\w.-]+/[\w.-]+/(tree|blob|commit|commits|releases/tag)/[^\s\"'<>]+",
    re.IGNORECASE,
)


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def decide(payload):
    for s in strings(payload.get("tool_input") or {}):
        m = PINNED.search(s)
        if m:
            base = re.match(r"github\.com/[\w.-]+/[\w.-]+", m.group(0), re.IGNORECASE).group(0)
            return (
                f"커밋·태그·브랜치에 고정된 GitHub URL을 입력하려고 합니다: {m.group(0)}. "
                f"제출할 때는 저장소 기본 URL만 씁니다: https://{base} "
                "(사용자 규칙, 2026-09-17)"
            )
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
