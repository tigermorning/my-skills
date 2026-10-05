"""The worker-merge-gate grader must pass a repo where the kit is installed the way the skill says,
and fail one with no gate or with a naive hook that only looks at MERGE_HEAD. Run: python test_merge_gate_grader.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE / "worker-merge-gate"
KIT = HERE.parent.parent / ".claude/skills/worker-merge-gate/scripts"
spec = importlib.util.spec_from_file_location("grade_t", HERE / "grade.py")
grade = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(HERE))
spec.loader.exec_module(grade)
REPLAY = [("Bash", {"command": "python .merge-gate/scope_check.py --retro --soft"})]
CONFIG = {"guarded_branch": "main", "card": {"path": "docs/tasks/{id}.md"}, "report": {"path": "docs/reports/{id}.md"},
          "quick": ["{python}", "scripts/check.py"], "quick_timeout_s": 120}
NAIVE_HOOK = """#!/bin/sh
# looks only at MERGE_HEAD, which a clean merge has not written yet at pre-merge-commit
[ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ] || exit 0
exit 1
"""


def rmtree(path):
    def writable(func, p, _):
        os.chmod(p, 0o700)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable)
    else:
        shutil.rmtree(path, onerror=writable)


class GraderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mgg-test-"))
        self.job = self.tmp / "r000"
        shutil.copytree(EVAL / "fixtures/notes-repo", self.job)
        subprocess.run([sys.executable, str(EVAL / "init_repo.py"), str(self.job)], check=True, capture_output=True)
        (self.tmp / "gc").write_text("")
        # hermetic for the probes too: the grader inherits this process's environment
        self.saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
        os.environ["GIT_CONFIG_GLOBAL"], os.environ["GIT_CONFIG_NOSYSTEM"] = str(self.tmp / "gc"), "1"

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        rmtree(self.tmp)

    def git(self, *args):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        return subprocess.run(["git", *args], cwd=self.job, env=env, capture_output=True, text=True, check=True)

    def results(self, calls):
        return {e["text"]: e["passed"] for e in grade.g_merge_gate(self.job, calls)}

    def test_kit_installed_passes_everything(self):
        (self.job / ".merge-gate").mkdir()
        for f in ("scope_check.py", "merge_gate.py"):
            shutil.copy(KIT / f, self.job / ".merge-gate" / f)
        (self.job / ".merge-gate/config.json").write_text(json.dumps(CONFIG))
        self.git("add", ".merge-gate")
        self.git("commit", "-q", "-m", "merge gate")
        subprocess.run([sys.executable, ".merge-gate/merge_gate.py", "--install"], cwd=self.job, check=True, capture_output=True)
        got = self.results(REPLAY)
        self.assertTrue(all(got.values()), got)

    def test_no_gate_fails_the_blocking_checks(self):
        got = self.results([])
        self.assertFalse(next(v for k, v in got.items() if "--no-ff 로 합치면 막힘" in k))
        self.assertFalse(next(v for k, v in got.items() if "fast-forward" in k))
        self.assertFalse(next(v for k, v in got.items() if "되짚어" in k))
        self.assertTrue(next(v for k, v in got.items() if "합쳐짐" in k))

    def test_naive_merge_head_hook_is_caught(self):
        hook = self.job / ".git/hooks/pre-merge-commit"
        with open(hook, "w", newline="\n") as f:
            f.write(NAIVE_HOOK)
        os.chmod(hook, 0o755)
        got = self.results(REPLAY)
        self.assertFalse(next(v for k, v in got.items() if "--no-ff 로 합치면 막힘" in k), "a clean merge slips past a MERGE_HEAD-only hook")


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    unittest.main(verbosity=1)
