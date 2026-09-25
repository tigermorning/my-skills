"""Run a skill's evals across models and configs, grade them, and print a table.

Usage:
    python scripts/skill-evals/run_evals.py --skill verify-by-running \\
        --models haiku,sonnet --configs skill,baseline --repeat 2 --judge-model opus

What it does, per (eval x config x model x repeat):
1. makes a job dir with a neutral name under the temp dir (agents behave differently when
   they can tell they are being evaluated), copies the fixtures, runs the eval's init
   script, and starts a stand-in "user server" when the eval needs one;
2. runs `claude -p` in the job dir. config "skill" prefixes the prompt with "read this
   SKILL.md and follow it"; config "baseline" sends the bare prompt;
3. grades with grade.py (script and transcript checks) while the user server is still up;
4. runs the agent inside a Job Object (Windows) or a process group, and terminates that
   container after grading, so every server the agent left behind dies and nothing is
   ever killed by name, port or a guessed PID;
5. asks --judge-model to grade the "judge" assertions from the final report only, with the
   skill name and job path redacted, one call per run.

--fail-under R exits 1 when the pass rate of the "skill" config is below R, so the loop
"run, read failures, edit SKILL.md, rerun" can be scripted or driven with /loop.
--record writes last_run.json for the skill when the skill config ran.
"""
import argparse
import concurrent.futures as cf
import ctypes
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
GRADE_LOCK = threading.Lock()  # graders read GRADE_USER_* from the environment, so grade one run at a time
CLAUDE = shutil.which("claude") or "claude"
SUFFIX = "\n\n작업 폴더 밖의 파일은 수정하지 마세요. 끝나면 무엇을 했는지 보고하세요."


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_prompt(ev, config, skill_md, job, port, user_port):
    text = ev["prompt"].replace("{dir}", str(job).replace("\\", "/")).replace("{port}", str(port)).replace("{user_port}", str(user_port or ""))
    prefix = f"시작 전에 {str(skill_md).replace(chr(92), '/')} 를 읽고 그 지침을 따르세요.\n\n" if config == "skill" else ""
    return prefix + text + SUFFIX


def exposure_problems(calls, config, skill):
    """Why a run cannot be trusted as a measurement of `config`, or [] when it can.

    Agents can load a stale copy of the skill through the Skill tool (~/.claude/skills), which
    would score the wrong text for "skill" and leak the skill into "baseline".
    """
    problems = []
    if any(n == "Skill" for n, _ in calls):
        problems.append("agent called the Skill tool (may have loaded an installed copy, not the repo SKILL.md)")
    if config == "skill":
        want = f"skills/{skill}/skill.md"
        opened = [i for n, i in calls
                  if (n == "Read" and want in str(i.get("file_path", "")).replace("\\", "/").lower())
                  or (n in ("Bash", "PowerShell") and want in str(i.get("command", "")).replace("\\", "/").lower())]
        if not opened:
            problems.append(f"agent never read {want}")
    return problems


def run_problems(calls, config, skill, transcript):
    """exposure_problems plus a usage-limit check: a run cut off by the limit measured nothing."""
    if "hit your session limit" in Path(transcript).read_text(encoding="utf-8", errors="replace"):
        return ["usage limit hit during the run; rerun after it resets"]
    return exposure_problems(calls, config, skill)


def redact(text, skill):
    text = re.sub(r"\S*[\\/](?:jobs|skill-evals)[\\/]\S*", "[workdir]", text)
    text = re.sub(re.escape(skill), "[…]", text, flags=re.I)
    return re.sub(r"SKILL\.md|스킬", "[…]", text)


def extract_json_list(text):
    start = text.find("[")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            depth += text[i] == "["
            depth -= text[i] == "]"
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    break
        start = text.find("[", start + 1)
    return None


def final_report(transcript):
    for line in Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") == "result":
            return rec.get("result", "")
    return ""


class ProcessJob:
    """Everything the agent starts (servers, background jobs) dies with this object.

    Windows: a Job Object with kill-on-close, so no PID or port guessing is needed and PID reuse
    cannot make us kill an innocent process. Elsewhere: a new session, killed as a process group.
    """

    def __init__(self):
        self.handle = None
        if sys.platform == "win32":
            from ctypes import wintypes

            class Basic(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

            class IoCounters(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

            class Extended(ctypes.Structure):
                _fields_ = [("Basic", Basic), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            k = ctypes.windll.kernel32
            k.CreateJobObjectW.restype = wintypes.HANDLE
            self.k = k
            self.handle = k.CreateJobObjectW(None, None)
            info = Extended()
            info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = JobObjectExtendedLimitInformation

    def popen(self, cmd, **kw):
        if sys.platform == "win32":
            proc = subprocess.Popen(cmd, **kw)
            self.k.OpenProcess.restype = ctypes.c_void_p
            h = self.k.OpenProcess(0x1F0FFF, False, proc.pid)
            self.k.AssignProcessToJobObject(ctypes.c_void_p(self.handle), ctypes.c_void_p(h))
            self.k.CloseHandle(ctypes.c_void_p(h))
            return proc
        self.proc = subprocess.Popen(cmd, start_new_session=True, **kw)
        return self.proc

    def kill_all(self):
        if sys.platform == "win32":
            if self.handle:
                self.k.TerminateJobObject(ctypes.c_void_p(self.handle), 1)
                self.k.CloseHandle(ctypes.c_void_p(self.handle))
                self.handle = None
        else:
            try:
                os.killpg(self.proc.pid, 9)
            except (OSError, AttributeError):
                pass


def start_user_server(spec, eval_dir, job_root, name, pf):
    port = free_port()
    src = eval_dir / spec["from"]
    dst = job_root / f"user-{name}"
    shutil.copytree(src, dst)
    cmd = [sys.executable if c == "python" else c.replace("{user_port}", str(port)) for c in spec["cmd"]]
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0
    subprocess.Popen(cmd, cwd=dst, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not pf.port_in_use(port):
        time.sleep(0.1)
    pid = pf.port_owner(port)
    if not pid:
        raise RuntimeError(f"user server did not come up on {port}")
    return port, pid


def kill_pid(pid):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def one_run(task, args, grade, pf):
    ev, config, model, n, eval_dir, skill = task["ev"], task["config"], task["model"], task["n"], task["eval_dir"], task["skill"]
    name = task["id"]
    job = task["job_root"] / name
    job.mkdir(parents=True)
    for f in ev.get("files", []):
        src = eval_dir / f
        if src.is_dir():
            shutil.copytree(src, job, dirs_exist_ok=True)
        else:
            shutil.copy(src, job / src.name)
    if ev.get("init_script"):
        subprocess.run([sys.executable, str(eval_dir / ev["init_script"]), str(job)], check=True, capture_output=True)
    user_port = user_pid = None
    if ev.get("user_server"):
        user_port, user_pid = start_user_server(ev["user_server"], eval_dir, task["job_root"], name, pf)
    prompt = build_prompt(ev, config, ROOT / ".claude/skills" / skill / "SKILL.md", job, free_port(), user_port)
    transcript = task["job_root"] / f"{name}.jsonl"
    started = time.monotonic()
    job_handle = ProcessJob()
    try:
        with open(transcript, "w", encoding="utf-8") as out:
            proc = job_handle.popen([CLAUDE, "-p", "--model", model, "--permission-mode", "bypassPermissions", "--output-format", "stream-json", "--verbose",
                                     "--disallowedTools", "Skill"],
                                    stdin=subprocess.PIPE, stdout=out, stderr=subprocess.DEVNULL, cwd=job)
            try:
                proc.communicate(prompt.encode("utf-8"), timeout=args.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()  # grade whatever the agent left behind
        calls = grade.tool_calls(transcript)
        with GRADE_LOCK:
            if user_pid:
                os.environ["GRADE_USER_PORT"], os.environ["GRADE_USER_PID"] = str(user_port), str(user_pid)
            expectations = grade.GRADERS[ev["name"]](job, calls) if any(a["check"] == "script" for a in ev["assertions"]) else []
    finally:
        job_handle.kill_all()  # graded first, so leftovers were visible to the "cleanup" check
        # kill the stand-in user server only while it is still what we started, so a reused PID is never hit
        if user_pid and pf.port_owner(user_port) == user_pid:
            kill_pid(user_pid)
    return {**{k: task[k] for k in ("id", "config", "model", "n")}, "eval": ev["name"], "job": str(job), "transcript": str(transcript),
            "seconds": round(time.monotonic() - started), "invalid": run_problems(calls, config, skill, transcript), "script": expectations, "report": final_report(transcript)}


def judge_run(res, ev, skill, judge_model):
    items = [a for a in ev["assertions"] if a["check"] == "judge"]
    if not items:
        return []
    prompt = (
        "You grade one coding agent's final report. Judge only from the report text; pass an assertion only with concrete evidence in it. "
        "Answer with ONLY a JSON list: [{\"id\": \"...\", \"passed\": true|false, \"evidence\": \"one sentence\"}], one entry per assertion.\n\n"
        f"TASK GIVEN TO THE AGENT:\n{redact(ev['prompt'], skill)}\n\nREPORT:\n{redact(res['report'], skill)}\n\nASSERTIONS:\n"
        + "\n".join(f"- id={a['id']}: {a['text']}" for a in items))
    r = subprocess.run([CLAUDE, "-p", "--model", judge_model, "--output-format", "json"], input=prompt.encode("utf-8"), capture_output=True, cwd=tempfile.gettempdir())
    lines = r.stdout.decode("utf-8", "replace").splitlines()
    try:
        text = json.loads(lines[0])["result"]  # the CLI can print more than one JSON line; the first is the answer
    except (ValueError, KeyError, IndexError):
        text = "\n".join(lines)
    got = {g["id"]: g for g in (extract_json_list(text) or []) if isinstance(g, dict) and "id" in g}
    return [{"text": a["text"], "passed": bool(got.get(a["id"], {}).get("passed")), "evidence": "judge: " + str(got.get(a["id"], {}).get("evidence", "no verdict"))} for a in items]


def table(results):
    rows = {}
    for r in results:
        e = r["script"] + r["judge"]
        k = (r["config"], r["model"])
        p, n = rows.get(k, (0, 0))
        rows[k] = (p + sum(x["passed"] for x in e), n + len(e))
    lines = ["| config | model | passed | rate |", "|---|---|---|---|"]
    for (c, m), (p, n) in sorted(rows.items()):
        lines.append(f"| {c} | {m} | {p}/{n} | {p / n:.0%} |" if n else f"| {c} | {m} | 0/0 | - |")
    return "\n".join(lines), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--models", default="sonnet")
    ap.add_argument("--configs", default="skill,baseline")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--evals", default="", help="comma-separated eval names; default all")
    ap.add_argument("--judge-model", default="opus")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--fail-under", type=float, default=None)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    eval_dir = HERE / args.skill
    data = json.loads((eval_dir / "evals.json").read_text(encoding="utf-8"))
    wanted = set(filter(None, args.evals.split(",")))
    evals = [e for e in data["evals"] if not wanted or e["name"] in wanted]
    job_root = Path(tempfile.gettempdir()) / "skill-evals" / datetime.now().strftime("%Y%m%d-%H%M%S")
    tasks, i = [], 0
    for ev in evals:
        for config in args.configs.split(","):
            for model in args.models.split(","):
                for n in range(args.repeat):
                    tasks.append({"id": f"r{i:03d}", "ev": ev, "config": config, "model": model, "n": n, "eval_dir": eval_dir, "skill": args.skill, "job_root": job_root})
                    i += 1
    print(f"{len(tasks)} runs: {len(evals)} evals x {args.configs} x {args.models} x {args.repeat}; jobs in {job_root}")
    if args.dry_run:
        return
    job_root.mkdir(parents=True)
    global grade
    grade = load(HERE / "grade.py", "grade_eval")
    pf = load(ROOT / ".claude/skills/verify-by-running/scripts/preflight.py", "preflight_eval")

    results = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        for fut in cf.as_completed([ex.submit(one_run, t, args, grade, pf) for t in tasks]):
            results.append(fut.result())
            print(f"  done {results[-1]['id']} {results[-1]['eval']} {results[-1]['config']}/{results[-1]['model']} ({results[-1]['seconds']}s)", flush=True)
    by_name = {e["name"]: e for e in evals}
    for r in results:
        r["judge"] = judge_run(r, by_name[r["eval"]], args.skill, args.judge_model)
    (job_root / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    md, rows = table(results)
    print("\n" + md)
    for r in sorted(results, key=lambda x: x["id"]):
        for e in r["script"] + r["judge"]:
            if not e["passed"]:
                print(f"FAIL {r['id']} {r['eval']} {r['config']}/{r['model']}: {e['text']} | {str(e['evidence'])[:110]}")
    invalid = [r for r in sorted(results, key=lambda x: x["id"]) if r["invalid"]]
    for r in invalid:
        print(f"INVALID {r['id']} {r['eval']} {r['config']}/{r['model']}: {'; '.join(r['invalid'])}")
    if invalid:
        print(f"{len(invalid)} run(s) did not measure their config; fix the setup and rerun. Nothing recorded.")
        sys.exit(2)
    skill_rows = [(p, n) for (c, m), (p, n) in rows.items() if c == "skill"]
    passed, total = (sum(p for p, _ in skill_rows), sum(n for _, n in skill_rows))
    if args.record and total:
        subprocess.run([sys.executable, str(HERE / "record_run.py"), args.skill, "--model", args.models, "--passed", str(passed), "--total", str(total),
                        "--note", f"run_evals.py: {len(results)} runs, repeat={args.repeat}, judge={args.judge_model}"], check=True)
    if args.fail_under is not None and total and passed / total < args.fail_under:
        print(f"skill pass rate {passed}/{total} is below {args.fail_under:.0%}")
        sys.exit(1)


if __name__ == "__main__":
    main()
