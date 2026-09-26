"""Read-only preflight before running anything to verify a change.

Usage:
    python preflight.py --port 8500 [--user-port 8000] [--dir PATH] [--json]

Reports, without changing anything:
- each --port: free or in use (and the owning PID when the OS can tell);
  --port marks ports you intend to use, so "in use" there is a problem
- each --user-port: the user's own instance; it must stay untouched, so the
  report reminds you not to restart, stop or send requests to it
- git branch, HEAD, and uncommitted changes in --dir (default: cwd)
- python / node versions on PATH

Exit code 2 when a --port you intend to use is already taken, so a caller
cannot start a second server on top of someone else's.
"""
import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def port_owner(port):
    """Best-effort PID of the listener; None when the OS tool is unavailable."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[3].upper() == "LISTENING" and parts[1].endswith(f":{port}"):
                    return int(parts[4])
        elif shutil.which("lsof"):
            out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True, timeout=10).stdout
            return int(out.split()[0]) if out.split() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def run(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_state(d):
    if run(["git", "rev-parse", "--is-inside-work-tree"], cwd=d) != "true":
        return {"repo": False}
    dirty = run(["git", "status", "--porcelain"], cwd=d) or ""
    return {
        "repo": True,
        "branch": run(["git", "branch", "--show-current"], cwd=d),
        "head": run(["git", "rev-parse", "--short", "HEAD"], cwd=d),
        "uncommitted": [l for l in dirty.splitlines() if l.strip()],
    }


def versions():
    out = {}
    for name, cmd in (("python", [sys.executable, "--version"]), ("node", ["node", "--version"])):
        v = run(cmd) if name == "python" or shutil.which("node") else None
        out[name] = re.sub(r"^Python\s+", "", v) if v else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, action="append", default=[], help="port you intend to use")
    ap.add_argument("--user-port", type=int, action="append", default=[], help="the user's instance; never touch it")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    report = {"ports": [], "git": git_state(str(Path(a.dir).resolve())), "versions": versions(), "problems": []}
    for port in a.port:
        busy = port_in_use(port)
        report["ports"].append({"port": port, "role": "mine", "in_use": busy, "pid": port_owner(port) if busy else None})
        if busy:
            report["problems"].append(f"port {port} is already in use; pick another free port instead of reusing or stopping it")
    for port in a.user_port:
        busy = port_in_use(port)
        report["ports"].append({"port": port, "role": "user", "in_use": busy, "pid": port_owner(port) if busy else None})
    if report["git"].get("uncommitted"):
        report["problems"].append("uncommitted changes present; do not checkout other commits in this tree, use `git worktree add`")

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        for p in report["ports"]:
            state = f"in use (pid {p['pid']})" if p["in_use"] else "free"
            note = "  <- user's instance: do not restart, stop or send requests" if p["role"] == "user" else ""
            print(f"port {p['port']} [{p['role']}]: {state}{note}")
        g = report["git"]
        if g["repo"]:
            print(f"git: {g['branch']} @ {g['head']}, {len(g['uncommitted'])} uncommitted")
        else:
            print("git: not a repo")
        print(f"versions: python {report['versions']['python']}, node {report['versions']['node']}")
        for pr in report["problems"]:
            print(f"PROBLEM: {pr}")
    sys.exit(2 if any(p["role"] == "mine" and p["in_use"] for p in report["ports"]) else 0)


if __name__ == "__main__":
    main()
