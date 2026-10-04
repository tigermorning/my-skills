"""Merge gate: when a worker branch is merged into a guarded branch, git hooks run the scope check
and a quick check, and refuse the merge commit if either fails.

  python .merge-gate/merge_gate.py --install   guard the branch this worktree is on now (adds to the list)
  python .merge-gate/merge_gate.py --status    one line: is the gate on here (put it in your check table)
The hooks call it with --hook=<name> --branch=<current> --repo=<worktree top>.

Why it is built this way (each point is a hole found by testing):
- A clean `git merge` runs pre-merge-commit before MERGE_HEAD exists; the incoming names are in
  GIT_REFLOG_ACTION ("merge <names>"); a pull's incoming commits are the for-merge lines of FETCH_HEAD.
- A merge that needed conflict resolution skips pre-merge-commit; the final `git commit` runs pre-commit.
- A fast-forward runs no hook at all, so install sets branch.<guarded>.mergeOptions=--no-ff.
- Names lie (a tag called like the branch, `refs/heads/…`, `@{-1}`, letter case on Windows, a hand-written
  merge message), so every incoming commit is also matched against the worker refs that point at it.
- The judges (this file, scope_check.py, config, the quick check entry) and the card run from HEAD,
  never from the merged working tree, so a worker cannot edit a judge or its card to pass itself.
- Anything the gate cannot see (a squash, a merge whose incoming commit it cannot name) is refused.
- While it runs it leaves merge-gate.running in the git dir so other automation can stay out.
"""
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KIT = ".merge-gate"
SHIM = "# merge-gate:shim"
HOOKS = ("pre-merge-commit", "pre-commit")
SAFE = re.compile(r"[A-Za-z0-9._/@+:\\ -]+")  # anything else could break the quoting in the shell shim
REPO_VARS = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR", "GIT_NAMESPACE",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_QUARANTINE_PATH"}
CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in REPO_VARS}
DEFAULTS = {"guarded_branch": "main", "worker_branch": r"^worker/(T-\d+[a-z]?)", "quick": [], "quick_timeout_s": 1800}
IGNORE_CASE = re.IGNORECASE if os.name == "nt" else 0  # Windows refs ignore letter case

# The hook hands this bootstrap the repo and execs HEAD's copy of this file as bytes, because a script
# piped to `python -` would be decoded with the console code page. A crash blocks the commit (exit 1).
BOOTSTRAP = (
    'import subprocess,sys\n'
    'repo=[a[7:] for a in sys.argv if a.startswith("--repo=")][0]\n'
    'r=subprocess.run(["git","show","HEAD:.merge-gate/merge_gate.py"],cwd=repo,capture_output=True)\n'
    'try:\n'
    '    src=r.stdout if r.returncode==0 else open(repo+"/.merge-gate/merge_gate.py","rb").read()\n'
    'except OSError:\n'
    '    sys.exit("merge-gate: .merge-gate/merge_gate.py is gone - reinstall it, or delete the merge-gate hooks")\n'
    'exec(compile(src,"merge_gate.py","exec"))\n'
)


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, env=CLEAN_ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def hooks_dir(top):
    """(folder for this worktree's hooks, relay folder or None, reason when installing would be a guess)."""
    hp = git(top, "config", "--type=path", "--get", "core.hooksPath", check=False)
    if not hp:
        p = Path(git(top, "rev-parse", "--git-path", "hooks"))
        return (p if p.is_absolute() else Path(top) / p), None, None
    hpp = Path(hp) if Path(hp).is_absolute() else Path(top) / hp
    if (hpp / "_dispatch").exists():  # a global folder whose stubs forward to <git-dir>/hooks
        return Path(git(top, "rev-parse", "--absolute-git-dir")) / "hooks", hpp, None
    return None, hpp, f"core.hooksPath={hp} 는 다른 도구의 훅 폴더 — 그 훅 끝에서 merge_gate.py --hook=<이름> 을 부르게 손으로 이을 것"


def guarded_in(shim_text):
    m = re.search(r"^# guarded: (.*)$", shim_text or "", re.M)
    return m.group(1).split() if m else []


def shim(hook, branches, py):
    listed = " ".join(branches)
    return "\n".join([
        "#!/bin/sh",
        f"{SHIM} — 합치기 관문(설치: python {KIT}/merge_gate.py --install)",
        f"# guarded: {listed}",
        'cur=$(git symbolic-ref -q HEAD) || exit 0',
        'cur=${cur#refs/heads/}',
        f'case " {listed} " in *" $cur "*) ;; *) exit 0 ;; esac',
        'top=$(git rev-parse --show-toplevel)',
        f"exec '{py}' -c '{BOOTSTRAP}' --hook={hook} --branch=\"$cur\" --repo=\"$top\"",
        "",
    ])


def install(top):
    branch = git(top, "branch", "--show-current", check=False)
    py = sys.executable.replace("\\", "/")
    if not branch:
        print("✘ HEAD 가 브랜치에 있지 않음 — 지킬 브랜치를 정할 수 없어 멈춤")
        return 1
    for what, value in (("브랜치 이름", branch), ("python 경로", py)):
        if not SAFE.fullmatch(value) or "'" in value:
            print(f"✘ {what} '{value}' 에 셸에서 깨질 글자가 있음 — 다른 이름·경로로")
            return 1
    if git(top, "cat-file", "-e", f"HEAD:{KIT}/merge_gate.py", check=False) is None:
        print(f"✘ {KIT}/ 가 HEAD 에 커밋되지 않음 — 키트와 config.json 을 먼저 커밋할 것(관문은 HEAD 판으로 판정한다)")
        return 1
    target, relay, reason = hooks_dir(top)
    if reason:
        print(f"✘ {reason}")
        return 1
    rc = 0
    if relay:
        for h in HOOKS:
            if not (relay / h).exists():
                shutil.copyfile(relay / "_dispatch", relay / h)
                os.chmod(relay / h, 0o755)
                print(f"✔ 전역 중계 {h} 새로 만듦({relay}) — 이 PC 의 다른 저장소에 로컬 {h} 훅이 있었다면 이제부터 돈다")
    target.mkdir(parents=True, exist_ok=True)
    for h in HOOKS:
        f = target / h
        old = f.read_text(encoding="utf-8", errors="replace") if f.exists() else None
        if old is not None and SHIM not in old:
            print(f"✘ {f} 에 다른 훅이 있음 — 덮지 않음. 그 훅 끝에서 '{py}' {KIT}/merge_gate.py --hook={h} --branch=<지금 브랜치> --repo=<worktree> 를 부를 것")
            rc = 1
            continue
        branches = list(dict.fromkeys([*guarded_in(old), branch]))  # a shared hooks folder serves every worktree
        f.write_text(shim(h, branches, py), encoding="utf-8", newline="\n")
        os.chmod(f, os.stat(f).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"✔ 훅 {h} → {f} (지키는 브랜치: {' '.join(branches)})")
    if git(top, "config", "--get", f"branch.{branch}.mergeOptions", check=False) != "--no-ff":
        git(top, "config", f"branch.{branch}.mergeOptions", "--no-ff")
    print(f"✔ branch.{branch}.mergeOptions = --no-ff(fast-forward 는 훅을 안 부름 — 명령줄 --ff-only 는 그대로 앞섬)")
    return rc


def status(top):
    br = git(top, "branch", "--show-current", check=False) or ""
    target, relay, reason = hooks_dir(top)
    problems = []
    if reason:
        problems.append(reason)
    else:
        for h in HOOKS:
            f = target / h
            text = f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""
            if br not in guarded_in(text):
                problems.append(f"{h} 훅 없음")
            else:
                m = re.search(r"^exec '([^']+)'", text, re.M)
                if m and not Path(m.group(1)).exists():
                    problems.append(f"{h} 훅의 python({m.group(1)}) 없음")
            if relay and not (relay / h).exists():
                problems.append(f"전역 중계 {h} 없음")
    if git(top, "cat-file", "-e", f"HEAD:{KIT}/merge_gate.py", check=False) is None:
        problems.append(f"{KIT}/ 가 HEAD 에 없음")
    print(f"✔ 관문 켜짐({br})" if not problems else
          f"· 관문 꺼짐({br or 'HEAD 떨어짐'}) — {' · '.join(problems)} → 지킬 브랜치에서 python {KIT}/merge_gate.py --install")
    return 0


def load_config(text):
    cfg = dict(DEFAULTS)
    if text:
        cfg.update(json.loads(text))
    return cfg


def incoming(top, gitdir):
    """[(sha, name or None)] coming into the merge."""
    mh = gitdir / "MERGE_HEAD"
    if mh.exists():  # the commit that ends a merge with conflicts; the message is not trusted for names
        return [(s, None) for s in mh.read_text(encoding="utf-8").split()]
    words = os.environ.get("GIT_REFLOG_ACTION", "").split()
    if words[:1] == ["pull"]:
        fh = gitdir / "FETCH_HEAD"
        out = []
        for line in (fh.read_text(encoding="utf-8", errors="replace").splitlines() if fh.exists() else []):
            if line and "not-for-merge" not in line:
                m = re.search(r"branch '([^']+)'", line)
                out.append((line.split()[0], m.group(1) if m else None))
        return out
    if words[:1] == ["merge"]:
        out = []
        for n in (w for w in words[1:] if not w.startswith("-")):
            sha = git(top, "rev-parse", "-q", "--verify", f"{n}^{{commit}}", check=False)
            full = git(top, "rev-parse", "--symbolic-full-name", n, check=False)
            if sha:
                out.append((sha, full or n))
        return out
    return []


def worker_of(top, sha, name, pattern):
    """(card id, ref) when the incoming commit is a worker branch tip, by its name or by any ref that points at it."""
    def card(ref):
        short = re.sub(r"^refs/heads/|^refs/remotes/[^/]+/", "", ref)
        for cand in (short, short.split("/", 1)[1] if "/" in short else None):  # origin/worker/T-1 → worker/T-1
            m = cand and re.match(pattern, cand, IGNORE_CASE)
            if m:
                return m.group(1)
        return None
    refs = [name] if name else []
    refs += (git(top, "for-each-ref", f"--points-at={sha}", "--format=%(refname)", "refs/heads/", "refs/remotes/", check=False) or "").splitlines()
    return next(((card(r), r) for r in refs if r and card(r)), None)


def run_quick(argv, cwd, timeout):
    """Run the quick check; on timeout kill its whole process tree, not just the first child."""
    out = tempfile.TemporaryFile()
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    p = subprocess.Popen(argv, cwd=cwd, env=CLEAN_ENV, stdout=out, stderr=subprocess.STDOUT, **kw)
    try:
        code = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        code = None
    out.seek(0)
    return code, out.read().decode("utf-8", errors="replace")


def gate(hook, current, top):
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    def say(s):
        print(s, file=sys.stderr)

    if (git(top, "branch", "--show-current", check=False) or "") != current:
        return 0
    gitdir = Path(git(top, "rev-parse", "--absolute-git-dir"))

    def block(lines):
        say("\n".join(["", *lines, "  관문 건너뛰기(--no-verify)는 사람이 허락할 때만", ""]))
        return 1

    if hook == "pre-commit" and not (gitdir / "MERGE_HEAD").exists():
        if (gitdir / "SQUASH_MSG").exists():
            return block([f"✘ 합치기 관문: {current} 에 squash 합치기 — 들어온 브랜치를 알 수 없어 판정 못 함",
                          "  고치는 길: git reset --merge → git merge --no-ff <일꾼 브랜치>"])
        return 0  # an ordinary commit
    head_cfg = git(top, "show", f"HEAD:{KIT}/config.json", check=False)
    cfg = load_config(head_cfg)
    cands = incoming(top, gitdir)
    if not cands:
        if hook == "pre-merge-commit":
            return block([f"✘ 합치기 관문: 들어오는 커밋을 못 정함(GIT_REFLOG_ACTION=\"{os.environ.get('GIT_REFLOG_ACTION', '')}\")",
                          "  고치는 길: git merge --abort → git merge --no-ff <브랜치>"])
        return 0
    workers = [(sha, w) for sha, name in cands for w in [worker_of(top, sha, name, cfg["worker_branch"])] if w]
    if not workers:
        return 0

    marker = gitdir / "merge-gate.running"
    tmp = Path(tempfile.mkdtemp(prefix="merge-gate-"))
    marker.write_text(f"{os.getpid()} {' '.join(r for _, (_, r) in workers)}\n", encoding="utf-8")
    try:
        def from_head(rel):
            """HEAD's copy of a judge file, written under tmp; the working copy only if HEAD has none."""
            data = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=top, env=CLEAN_ENV, capture_output=True)
            if data.returncode != 0:
                say(f"· {rel}: HEAD 에 없음 — 작업 트리 판으로 돌림")
                return str(Path(top) / rel)
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data.stdout)
            return str(dest)

        t0, fails = time.time(), []
        say(f"\n합치기 관문({hook}): {' · '.join(r for _, (_, r) in workers)} → {current} — 범위 검사 · 빠른 검사")
        sc, conf = from_head(f"{KIT}/scope_check.py"), from_head(f"{KIT}/config.json")
        for sha, (card, _) in workers:
            r = subprocess.run([sys.executable, sc, "--config", conf, "--repo", top, "--tip", sha, "--into", "HEAD", "--card", card],
                               cwd=top, env=CLEAN_ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
            say((r.stdout + r.stderr).rstrip())
            if r.returncode != 0:
                fails.append(f"범위 검사 {card}(exit {r.returncode})")
        if fails:
            say("· 빠른 검사 건너뜀(범위 검사에서 막힘)")
        elif cfg["quick"]:
            argv = [sys.executable if a == "{python}" else a.replace("{repo}", top) for a in cfg["quick"]]
            argv = [from_head(a[6:-1]) if re.fullmatch(r"\{head:[^}]+\}", a) else a for a in argv]
            try:
                code, text = run_quick(argv, top, cfg["quick_timeout_s"])
            except OSError as e:
                code, text = 127, f"빠른 검사를 시작하지 못함: {e}"
            out = text.splitlines()
            say("\n".join([l for l in out if re.match(r"^([✔✘·] |\| )", l)] or out[-20:]))
            if code is None:
                fails.append(f"빠른 검사({cfg['quick_timeout_s']}초 안에 안 끝나 끔)")
            elif code != 0:
                fails.append(f"빠른 검사(exit {code})")
        took = round(time.time() - t0)
        if fails:
            return block([f"✘ 합치기 관문: {' · '.join(fails)} — merge 커밋을 만들지 않음({took}초)",
                          "  고치는 길: git merge --abort → 일꾼 브랜치에서 ✘ 줄을 고치거나(보고서에 적기·되돌리기) 일꾼에게 돌려보냄 → 다시 merge"])
        say(f"✔ 합치기 관문 통과({took}초) — 무거운 검사는 합친 뒤 따로 돌릴 것\n")
        return 0
    finally:
        marker.unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    arg = {a.split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True) for a in sys.argv[1:] if a.startswith("--")}
    top = git(arg.get("--repo") or os.getcwd(), "rev-parse", "--show-toplevel")
    if "--install" in arg:
        sys.exit(install(top))
    if "--status" in arg:
        sys.exit(status(top))
    if "--hook" in arg:
        sys.exit(gate(arg["--hook"], arg.get("--branch"), top))
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()
