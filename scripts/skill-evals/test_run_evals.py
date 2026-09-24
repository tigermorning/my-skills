"""Self-test for run_evals.py pieces that need no model call. Run: python test_run_evals.py"""
import importlib.util
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("run_evals", HERE / "run_evals.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failed = []


def check(label, ok, detail=""):
    if not ok:
        failed.append(f"{label} {detail}")


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


# prompt building: skill config prefixes the SKILL.md path, baseline does not; placeholders are filled
ev = {"prompt": "{dir}/a.py on {port} and {user_port}"}
sk = mod.build_prompt(ev, "skill", Path("C:/x/SKILL.md"), Path("C:/job"), 1234, 5678)
bl = mod.build_prompt(ev, "baseline", Path("C:/x/SKILL.md"), Path("C:/job"), 1234, 5678)
check("skill prompt names SKILL.md", "SKILL.md" in sk and "C:/job/a.py on 1234 and 5678" in sk)
check("baseline prompt has no skill mention", "SKILL.md" not in bl and bl.startswith("C:/job/a.py"))

# redaction hides the skill name and job paths from the judge
red = mod.redact(r"used verify-by-running in C:\Temp\skill-evals\2026\r001\app.py and SKILL.md", "verify-by-running")
check("redaction", "verify-by-running" not in red and "skill-evals" not in red and "SKILL.md" not in red, red)

# judge output parsing tolerates prose around the JSON list
got = mod.extract_json_list('Sure.\n[{"id": "a", "passed": true, "evidence": "x [y]"}]\nDone')
check("json list extraction", got and got[0]["id"] == "a" and got[0]["passed"] is True, str(got))
check("json list extraction: none", mod.extract_json_list("no list here") is None)

# containment: a server started by a process inside the job must die when the job is terminated
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
code = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import socket,time;s=socket.socket();s.bind((\"127.0.0.1\",{port}));s.listen();time.sleep(60)']);time.sleep(60)"
job = mod.ProcessJob()
proc = job.popen([sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.monotonic() + 10
while time.monotonic() < deadline and not listening(port):
    time.sleep(0.1)
check("grandchild server came up", listening(port))
job.kill_all()
time.sleep(0.5)
check("grandchild server died with the job", not listening(port))

for f in failed:
    print("FAIL", f)
print(f"{6 - len(failed)}/6 passed" if not failed else f"{len(failed)} failed")
sys.exit(1 if failed else 0)
