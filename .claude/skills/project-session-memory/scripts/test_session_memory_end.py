"""Self-test for session-memory-end.sh: the capture commit lands only where it cannot do harm.

A merge gate can hold a merge open for minutes (pre-merge-commit runs checks before the merge commit),
and a conflicted merge stays open until someone commits. If a session ends in that window and the hook
commits, it moves HEAD under the merge and the merge fails.

A feature branch is headed for a PR, so a capture commit there gets pushed into someone else's review.
Off the default branch the capture waits in the shared git dir and the next default-branch session end
commits it. Run: python test_session_memory_end.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = (HERE / "session-memory-end.sh").as_posix()
START_HOOK = (HERE / "session-memory-start.sh").as_posix()
BASH = shutil.which("bash") or "/bin/bash"
REPO_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR")

# A stand-in for jq that answers the three filters the hook uses, so the test runs where jq is missing.
JQ_SHIM = """import json, sys
args = sys.argv[1:]
flt = next(a for a in args if not a.startswith('-'))
data = sys.stdin.read()
if '-n' in args:  # the start hook builds its output from --arg d and --rawfile ctx
    d = args[args.index('--arg') + 2]
    ctx = open(args[args.index('--rawfile') + 2], encoding='utf-8').read()
    print(json.dumps({'hookSpecificOutput': {'additionalContext': d + ctx}}))
elif 'transcript_path' in flt:
    print(json.loads(data).get('transcript_path', ''))
elif 'session_id' in flt:
    print(json.loads(data).get('session_id', ''))
else:
    print('excerpt')
"""


def rmtree(path):
    def writable(func, p, _):  # git object files are read-only on Windows
        os.chmod(p, 0o700)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable)
    else:
        shutil.rmtree(path, onerror=writable)


class SessionEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sme-test-"))
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "jq.py").write_text(JQ_SHIM)
        jq = bin_dir / "jq"
        with open(jq, "w", newline="\n") as f:
            f.write(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{(bin_dir / "jq.py").as_posix()}" "$@"\n')
        os.chmod(jq, 0o755)
        (self.tmp / "gitconfig").write_text("")
        self.env = {k: v for k, v in os.environ.items() if k not in REPO_VARS}
        self.env.update({"GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
                         "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                         "PATH": bin_dir.as_posix() + os.pathsep + os.environ.get("PATH", ""), "CLAUDE_PROJECT_DIR": str(self.repo)})
        self.transcript = self.tmp / "t.jsonl"
        self.transcript.write_text('{"type":"user","message":{"content":"hi"}}\n')
        self.git("init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("base\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    def tearDown(self):
        rmtree(self.tmp)

    def git(self, *args, ok=True):
        r = subprocess.run(["git", *args], cwd=self.repo, env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if ok and r.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} → {r.returncode}\n{r.stdout}\n{r.stderr}")
        return r

    def end_session(self, sid):
        stdin = f'{{"transcript_path": "{self.transcript.as_posix()}", "session_id": "{sid}"}}'
        r = subprocess.run([BASH, HOOK], cwd=self.repo, env=self.env, input=stdin, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)

    def subjects(self):
        return self.git("log", "--format=%s").stdout.split("\n")

    def committed(self, rel):
        return self.git("cat-file", "-e", f"HEAD:{rel}", ok=False).returncode == 0

    def gitdir(self):
        return Path(self.git("rev-parse", "--absolute-git-dir").stdout.strip())

    def test_commits_when_nothing_is_open(self):
        self.end_session("s1")
        self.assertTrue(self.committed(".claude/memory/inbox/s1.md"))

    def test_session_ending_while_a_merge_gate_runs(self):
        self.git("switch", "-q", "-c", "side")
        (self.repo / "b.txt").write_text("side\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "side")
        self.git("switch", "-q", "main")
        # The gate marks itself, then the session ends while it is still checking (an independent process).
        hook = self.gitdir() / "hooks" / "pre-merge-commit"
        stdin = f'{{"transcript_path": "{self.transcript.as_posix()}", "session_id": "s2"}}'
        hook.write_text("#!/bin/sh\n"
                        'touch "$(git rev-parse --absolute-git-dir)/merge-gate.running"\n'
                        "for v in $(env | sed -n 's/^\\(GIT_[A-Z_]*\\)=.*/\\1/p'); do unset \"$v\"; done\n"
                        f"printf '%s' '{stdin}' | '{BASH}' '{HOOK}'\n"
                        'rm -f "$(git rev-parse --absolute-git-dir)/merge-gate.running"\n', newline="\n")
        os.chmod(hook, 0o755)
        res = self.git("merge", "--no-ff", "side", "-m", "merge side", ok=False)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.subjects()[0], "merge side")
        self.assertEqual(len(self.git("log", "-1", "--format=%P").stdout.split()), 2)
        self.assertNotIn("project-session-memory: capture session s2", self.subjects())
        self.assertTrue((self.repo / ".claude/memory/inbox/s2.md").exists(), "the capture stays on disk")
        hook.unlink()
        self.end_session("s3")  # the next session end carries the waiting capture too
        self.assertTrue(self.committed(".claude/memory/inbox/s2.md"))
        self.assertTrue(self.committed(".claude/memory/inbox/s3.md"))

    def test_session_ending_inside_a_conflicted_merge(self):
        self.git("switch", "-q", "-c", "side")
        (self.repo / "a.txt").write_text("side\n")
        self.git("commit", "-q", "-am", "side")
        self.git("switch", "-q", "main")
        (self.repo / "a.txt").write_text("main\n")
        self.git("commit", "-q", "-am", "main")
        self.git("merge", "side", ok=False)
        self.assertTrue((self.gitdir() / "MERGE_HEAD").exists())
        self.end_session("s4")
        self.assertTrue((self.gitdir() / "MERGE_HEAD").exists(), "the merge is still open")
        self.assertEqual(self.subjects()[0], "main")
        self.assertTrue((self.repo / ".claude/memory/inbox/s4.md").exists())

    def test_stale_gate_marker_is_ignored(self):
        marker = self.gitdir() / "merge-gate.running"
        marker.write_text("1 worker/T-1\n")
        old = time.time() - 2 * 3600
        os.utime(marker, (old, old))
        self.end_session("s5")
        self.assertTrue(self.committed(".claude/memory/inbox/s5.md"), "a marker left by a killed gate must not stop captures forever")

    def spool(self):
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
        return common / "session-memory-spool"

    def first_subject(self, ref):
        return self.git("log", "-1", "--format=%s", ref).stdout.strip()

    def test_no_commit_on_a_feature_branch(self):
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.git("switch", "-q", "-c", "feat/x")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        self.end_session("s6")
        self.assertEqual(self.git("rev-parse", "HEAD").stdout.strip(), head, "a feature branch gets no capture commit")
        self.assertNotIn("capture session s6", self.git("log", "--all", "--format=%s").stdout)
        self.assertFalse((self.repo / ".claude/memory/inbox/s6.md").exists(), "nothing left in the tree for a later git add -A")
        self.assertEqual(self.git("status", "--porcelain").stdout, "")
        self.assertTrue((self.spool() / "s6.md").exists(), "the capture waits in the git dir")
        self.end_session("s6")
        self.assertEqual(len(list(self.spool().glob("*.md"))), 1)
        self.git("switch", "-q", "main")
        self.end_session("s7")
        self.assertTrue(self.committed(".claude/memory/inbox/s6.md"), "the next default-branch session end commits it")
        self.assertTrue(self.committed(".claude/memory/inbox/s7.md"))
        self.assertEqual(list(self.spool().glob("*.md")), [])
        self.assertEqual(self.first_subject("feat/x"), "base")

    def test_default_branch_comes_from_origin_head(self):
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
        self.end_session("s8")  # on main, but the remote's default is master
        self.assertFalse(self.committed(".claude/memory/inbox/s8.md"))
        self.assertTrue((self.spool() / "s8.md").exists())
        self.git("branch", "-m", "main", "master")
        self.end_session("s9")
        self.assertTrue(self.committed(".claude/memory/inbox/s8.md"))

    def test_detached_head_does_not_commit(self):
        self.git("switch", "-q", "--detach")
        self.end_session("s10")
        self.assertEqual(self.subjects()[0], "base")
        self.assertTrue((self.spool() / "s10.md").exists())

    def test_feature_worktree_spools_to_the_shared_git_dir(self):
        wt = self.tmp / "wt"
        self.git("worktree", "add", "-q", "-b", "claude/wt", str(wt))
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(wt))
        stdin = f'{{"transcript_path": "{self.transcript.as_posix()}", "session_id": "s11"}}'
        r = subprocess.run([BASH, HOOK], cwd=wt, env=env, input=stdin, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.first_subject("claude/wt"), "base")
        self.assertFalse((wt / ".claude/memory/inbox/s11.md").exists(), "removing the worktree must not lose it")
        self.end_session("s12")  # the main checkout is on main
        self.assertTrue(self.committed(".claude/memory/inbox/s11.md"))

    def test_session_start_shows_waiting_captures(self):
        self.git("switch", "-q", "-c", "feat/y")
        self.end_session("s13")
        r = subprocess.run([BASH, START_HOOK], cwd=self.repo, env=self.env, input='{"source": "startup"}', capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("s13", r.stdout)
        self.assertIn("session-memory-spool", r.stdout)


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    unittest.main(verbosity=1)
