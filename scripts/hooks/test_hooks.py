"""Table-driven tests for the PreToolUse guard hooks. Run: python scripts/hooks/test_hooks.py"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

CASES = [
    # (script, payload, should_deny)
    ("guard_curl_non_ascii.py", {"tool_name": "Bash", "tool_input": {"command": "curl -d '{\"title\":\"필라테스\"}' http://127.0.0.1:8000/notes"}}, True),
    ("guard_curl_non_ascii.py", {"tool_name": "PowerShell", "tool_input": {"command": "curl.exe --data \"제목\" http://x"}}, True),
    ("guard_curl_non_ascii.py", {"tool_name": "Bash", "tool_input": {"command": "cd /tmp && curl -s http://x/검색"}}, True),
    ("guard_curl_non_ascii.py", {"tool_name": "Bash", "tool_input": {"command": "curl --data-binary @body.json http://x"}}, False),
    ("guard_curl_non_ascii.py", {"tool_name": "Bash", "tool_input": {"command": "git commit -m '로그인 수정'"}}, False),
    ("guard_curl_non_ascii.py", {"tool_name": "Bash", "tool_input": {"command": "echo 'curly 한글'"}}, False),
    ("guard_curl_non_ascii.py", {"tool_name": "Write", "tool_input": {"file_path": "a", "content": "curl -d '한글'"}}, False),
    ("guard_pinned_github_url.py", {"tool_name": "mcp__Claude_Browser__form_input", "tool_input": {"ref": "ref_1", "value": "https://github.com/me/repo/tree/2ac1e3b"}}, True),
    ("guard_pinned_github_url.py", {"tool_name": "mcp__claude-in-chrome__computer", "tool_input": {"action": "type", "text": "github.com/me/repo/blob/main/README.md"}}, True),
    ("guard_pinned_github_url.py", {"tool_name": "mcp__Claude_Browser__browser_batch", "tool_input": {"actions": [{"name": "computer", "input": {"action": "type", "text": "https://github.com/me/repo/commit/abc1234"}}]}}, True),
    ("guard_pinned_github_url.py", {"tool_name": "mcp__Claude_Browser__form_input", "tool_input": {"ref": "ref_1", "value": "https://github.com/me/repo"}}, False),
    ("guard_pinned_github_url.py", {"tool_name": "mcp__Claude_Browser__form_input", "tool_input": {"ref": "ref_1", "value": "https://github.com/me/repo/issues/3"}}, False),
]


def run(script, payload):
    r = subprocess.run([sys.executable, str(HERE / script)], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace"))
    out = r.stdout.decode("utf-8").strip()
    return bool(out) and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


if __name__ == "__main__":
    failed = 0
    for script, payload, want in CASES:
        got = run(script, payload)
        if got != want:
            failed += 1
            print(f"FAIL {script}: want deny={want} got={got} input={json.dumps(payload['tool_input'], ensure_ascii=False)[:100]}")
    print(f"{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)
