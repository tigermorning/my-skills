"""Self-test for preflight.py. Run: python test_preflight.py"""
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args, cwd=None):
    r = subprocess.run([sys.executable, str(HERE / "preflight.py"), "--json", *args], capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    return r.returncode, json.loads(r.stdout)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    failed = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    busy = listener.getsockname()[1]
    free = free_port()

    code, rep = run("--port", str(free))
    if code != 0 or rep["ports"][0]["in_use"]:
        failed.append(f"free port reported busy (exit {code})")

    code, rep = run("--port", str(busy))
    if code != 2 or not rep["ports"][0]["in_use"] or not rep["problems"]:
        failed.append(f"busy intended port not flagged (exit {code})")

    code, rep = run("--port", str(free), "--user-port", str(busy))
    if code != 0 or not rep["ports"][1]["in_use"] or rep["ports"][1]["role"] != "user":
        failed.append(f"user's running instance should be reported, not fail (exit {code})")

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q"], cwd=tmp)
        Path(tmp, "a.txt").write_text("x", encoding="utf-8")
        code, rep = run("--dir", tmp)
        if not rep["git"]["repo"] or not rep["git"]["uncommitted"] or not any("worktree" in p for p in rep["problems"]):
            failed.append("uncommitted changes not reported with the worktree advice")

    listener.close()
    for f in failed:
        print(f"FAIL {f}")
    print(f"{4 - len(failed)}/4 passed")
    sys.exit(1 if failed else 0)
