"""Self-test for run_evals.py pieces that need no model call. Run: python test_run_evals.py"""
import importlib.util
import json
import tempfile
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
total = 0


def check(label, ok, detail=""):
    global total
    total += 1
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

# exposure: the skill config must read the repo SKILL.md and no config may use the Skill tool
read_it = [("Read", {"file_path": "C:\\repo\\.claude\\skills\\demo\\SKILL.md"})]
check("exposure: clean skill run", mod.exposure_problems(read_it, "skill", "demo") == [])
check("exposure: skill run without reading the file", len(mod.exposure_problems([("Write", {})], "skill", "demo")) == 1)
check("exposure: Skill tool flagged in baseline", len(mod.exposure_problems([("Skill", {"skill": "demo"})], "baseline", "demo")) == 1)
check("exposure: Skill tool flagged even if the file was read", len(mod.exposure_problems(read_it + [("Skill", {})], "skill", "demo")) == 1)
check("exposure: clean baseline", mod.exposure_problems([("Bash", {"command": "ls"})], "baseline", "demo") == [])

# a run cut off by the usage limit is invalid, not a failure of the skill
with tempfile.TemporaryDirectory() as tmp:
    lim = Path(tmp) / "l.jsonl"
    lim.write_text('{"type":"assistant","message":{"content":[{"type":"text","text":"You\'ve hit your session limit"}]}}', encoding="utf-8")
    check("usage limit flagged", "usage limit" in mod.run_problems([], "baseline", "demo", lim)[0])

# a transcript with a system record whose "message" is a string must not crash the grader
import json
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    tp = Path(tmp) / "t.jsonl"
    tp.write_text("\n".join([
        json.dumps({"type": "system", "subtype": "permission_denied", "message": "denied"}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}),
    ]), encoding="utf-8")
    spec_g = importlib.util.spec_from_file_location("grade_t", HERE / "grade.py")
    grade_t = importlib.util.module_from_spec(spec_g)
    spec_g.loader.exec_module(grade_t)
    check("tool_calls survives string message", grade_t.tool_calls(tp) == [("Bash", {"command": "ls"})])

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
print(f"{total - len(failed)}/{total} passed" if not failed else f"{len(failed)} failed")
sys.exit(1 if failed else 0)
