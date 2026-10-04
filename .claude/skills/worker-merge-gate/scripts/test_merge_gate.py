"""Self-test for the merge gate kit: builds throwaway repos, installs the gate, and tries every way
in that the gate must block or must let through. Run: python test_merge_gate.py
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
spec = importlib.util.spec_from_file_location("scope_check", HERE / "scope_check.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

CARD = """# T-001 시험 카드

## 만지는 파일

- 고침: `src/b.mjs`, `assets/c.png`
- **고치지 않음**: 규칙, `src/locked.mjs`

## 끝 조건

- 시험
"""
WIDE_CARD = CARD.replace("- 고침: `src/b.mjs`", "- 고침: `src/b.mjs`, `src/a-core.mjs`").replace("규칙, ", "")
REPORT = """# T-001 보고

## 한 것

- b.mjs 한 줄

## 확인(명령 → 결과 숫자)

- 시험 3 통과

## 막힌 것

- 없음

## 합칠 때 주의

- 없음
"""
CONFIG = {
    "guarded_branch": "main",
    "card": {"path": "docs/tasks/{id}.md"},
    "report": {"path": "docs/reports/{id}.md"},
    "aliases": {"규칙": ["*-core.mjs"]},
    "judges": [".merge-gate/", "check.py"],
    "quick": ["{python}", "{head:check.py}"],
    "quick_timeout_s": 120,
}
QUICK_CHECK = "import sys\nsys.exit(1 if 'BREAK' in open('src/b.mjs', encoding='utf-8').read() else 0)\n"
DISPATCH = '#!/bin/sh\ngd=$(git rev-parse --git-dir) || exit 0\nh="$gd/hooks/$(basename "$0")"\n[ -x "$h" ] && exec "$h" "$@"\nexit 0\n'
BAD = ("src/a-core.mjs", "// not allowed\n", True)


def rmtree(path):
    def writable(func, p, _):  # git object files are read-only on Windows
        os.chmod(p, 0o700)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable)
    else:
        shutil.rmtree(path, onerror=writable)


class Repo:
    def __init__(self, root, hooks_path=None):
        self.root = root
        cfg = root.parent / f"{root.name}.gitconfig"
        cfg.write_text(f"[core]\n\thooksPath = {hooks_path.as_posix()}\n" if hooks_path else "")
        # Hermetic: no global hooksPath or identity from this machine, and nothing that points at an outer repo.
        self.env = {k: v for k, v in os.environ.items() if k not in sc.REPO_VARS}
        self.env.update({"GIT_CONFIG_GLOBAL": str(cfg), "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
                         "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    def run(self, *args, ok=True, cwd=None):
        r = subprocess.run(args, cwd=cwd or self.root, env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if ok and r.returncode != 0:
            raise AssertionError(f"{' '.join(args)} → {r.returncode}\n{r.stdout}\n{r.stderr}")
        return r

    def git(self, *args, ok=True, cwd=None):
        return self.run("git", *args, ok=ok, cwd=cwd)

    def gate(self, *args, cwd=None):
        return self.run(sys.executable, ".merge-gate/merge_gate.py", *args, ok=False, cwd=cwd)

    def write(self, rel, text, append=False):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a" if append else "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def branch(self, name, *edits, base="main"):
        self.git("switch", "-q", "-c", name, base)
        for rel, text, append in edits:
            self.write(rel, text, append)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"work on {name}")
        self.git("switch", "-q", "main")

    def head_subject(self):
        return self.git("log", "-1", "--format=%s").stdout.strip()

    def merging(self):
        return (self.root / ".git" / "MERGE_HEAD").exists()


def make_project(root, hooks_path=None, commit_kit=True):
    root.mkdir(parents=True)
    r = Repo(root, hooks_path)
    r.git("init", "-q", "-b", "main")
    r.write("src/a-core.mjs", "export const a = 1;\n")
    r.write("src/b.mjs", "export const b = 1;\n")
    r.write("src/locked.mjs", "export const l = 1;\n")
    r.write("docs/tasks/T-001.md", CARD)
    r.write("check.py", QUICK_CHECK)
    r.write(".merge-gate/config.json", json.dumps(CONFIG, ensure_ascii=False, indent=2))
    for f in ("scope_check.py", "merge_gate.py"):
        shutil.copyfile(HERE / f, root / ".merge-gate" / f)
    r.git("add", "-A" if commit_kit else "src")
    r.git("commit", "-q", "-m", "base")
    return r


class GateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg-test-"))
        r = cls.r = make_project(cls.tmp / "proj")
        out = r.gate("--install")
        assert out.returncode == 0 and "지키는 브랜치: main" in out.stdout, out.stdout + out.stderr
        r.branch("feature/other", ("src/new.mjs", "x\n", False))
        r.branch("worker/T-001-bad", BAD)
        r.branch("worker/T-001-ok", ("src/b.mjs", "// ok\n", True), ("docs/reports/T-001.md", REPORT, False))
        r.branch("worker/T-001-quickfail", ("src/b.mjs", "// BREAK\n", True), ("docs/reports/T-001.md", REPORT, False))
        r.branch("worker/T-001-conflict", ("src/b.mjs", "// other side\n", True))
        r.branch("worker/T-001-selfok", (".merge-gate/scope_check.py", "import sys; sys.exit(0)\n", False), BAD)
        r.branch("worker/T-001-widen", ("docs/tasks/T-001.md", WIDE_CARD, False), BAD,
                 ("docs/reports/T-001.md", REPORT.replace("- 없음\n", "- `docs/tasks/T-001.md` 고침\n"), False))
        r.git("update-ref", "refs/remotes/origin/worker/T-001-remote", "worker/T-001-bad")

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.tmp)
        assert not cls.tmp.exists(), f"temp repo left behind: {cls.tmp}"

    def blocked(self, res, why):
        self.assertNotEqual(res.returncode, 0, why)
        self.assertIn("합치기 관문", res.stdout + res.stderr, why)

    def abort(self):
        self.r.git("merge", "--abort", ok=False)
        self.r.git("reset", "-q", "--merge", ok=False)
        self.r.git("switch", "-q", "main", ok=False)

    def merge_blocked(self, *args, why):
        self.addCleanup(self.abort)
        before = self.r.head_subject()
        res = self.r.git("merge", *args, ok=False)
        self.blocked(res, why)
        self.assertEqual(self.r.head_subject(), before, why)
        return res

    def test_01_status_on(self):
        self.assertIn("✔ 관문 켜짐(main)", self.r.gate("--status").stdout)

    def test_02_non_worker_passes(self):
        res = self.r.git("merge", "-q", "feature/other", "-m", "merge other", ok=False)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.r.head_subject(), "merge other")

    def test_03_out_of_card_blocked(self):
        res = self.merge_blocked("worker/T-001-bad", "-m", "m", why="banned file and no report")
        self.assertIn("a-core.mjs", res.stderr)

    def test_04_names_that_hide_a_worker(self):
        self.r.git("tag", "main", "main")  # a tag named like the branch must not switch the gate off
        self.addCleanup(lambda: self.r.git("tag", "-d", "main"))
        for args in (["worker/T-001-bad"], ["refs/heads/worker/T-001-bad"], ["origin/worker/T-001-remote"]):
            with self.subTest(args=args):
                self.merge_blocked(*args, "-m", "m", why=f"merge {args}")
                self.abort()

    def test_05_previous_branch_shorthand(self):
        self.r.git("switch", "-q", "worker/T-001-bad")
        self.r.git("switch", "-q", "main")
        self.merge_blocked("@{-1}", "-m", "m", why="@{-1} is the worker branch")

    @unittest.skipUnless(os.name == "nt", "letter case only aliases a ref on Windows")
    def test_06_letter_case(self):
        self.merge_blocked("Worker/T-001-bad", "-m", "m", why="Worker/ vs worker/")

    def test_07_pull_forms_blocked(self):
        for args in (["pull", "-q", "--no-rebase", "--no-edit", ".", "worker/T-001-bad"],
                     ["pull", "-q", "--no-rebase", "--no-edit", "-X", "theirs", ".", "worker/T-001-bad"]):
            with self.subTest(args=args):
                self.addCleanup(self.abort)
                self.blocked(self.r.git(*args, ok=False), " ".join(args))
                self.abort()

    def test_08_squash_blocked(self):
        self.addCleanup(self.abort)
        self.r.git("merge", "-q", "--squash", "--ff", "worker/T-001-bad")
        self.blocked(self.r.git("commit", "-q", "-m", "squash", ok=False), "squash then commit")

    def test_09_edited_judge_cannot_pass_itself(self):
        res = self.merge_blocked("worker/T-001-selfok", "-m", "m", why="worker replaced scope_check.py with exit(0)")
        self.assertIn("scope_check.py", res.stderr)

    def test_10_widened_card_does_not_count(self):
        res = self.merge_blocked("worker/T-001-widen", "-m", "m", why="worker moved the banned file into its own card")
        self.assertIn("a-core.mjs", res.stderr)

    def test_11_quick_check_failure_blocks(self):
        res = self.merge_blocked("worker/T-001-quickfail", "-m", "m", why="scope fine but quick check fails")
        self.assertIn("빠른 검사", res.stderr)

    def test_12_clean_worker_passes(self):
        res = self.r.git("merge", "worker/T-001-ok", "-m", "merge ok", ok=False)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("통과", res.stderr)
        self.assertEqual(self.r.head_subject(), "merge ok")

    def test_13_conflict_commit_blocked_even_with_a_fake_message(self):
        self.addCleanup(self.abort)
        self.r.git("merge", "worker/T-001-conflict", "-m", "Merge branch 'main' sync", ok=False)
        self.assertTrue(self.r.merging(), "expected a conflict once the ok branch is in")
        self.r.git("checkout", "-q", "--theirs", "src/b.mjs")
        self.r.git("add", "src/b.mjs")
        self.blocked(self.r.git("commit", "-q", "--no-edit", ok=False), "conflict commit whose message names main")

    def test_14_fast_forward_still_gated(self):
        self.r.branch("worker/T-001-ff", ("src/a-core.mjs", "// ff\n", True))
        self.merge_blocked("worker/T-001-ff", why="would have been a fast-forward")

    def test_15_ordinary_commit_and_no_marker(self):
        self.r.write("notes.txt", "x\n")
        self.r.git("add", "notes.txt")
        self.assertEqual(self.r.git("commit", "-q", "-m", "plain", ok=False).returncode, 0)
        self.assertFalse((self.r.root / ".git" / "merge-gate.running").exists())

    def test_16_plain_pull_from_a_remote_passes(self):
        remote = self.tmp / "remote.git"
        self.r.git("clone", "-q", "--bare", str(self.r.root), str(remote), cwd=self.tmp)
        self.r.git("remote", "add", "origin2", str(remote))
        self.addCleanup(lambda: self.r.git("remote", "remove", "origin2", ok=False))
        other = self.tmp / "other"
        self.r.git("clone", "-q", str(remote), str(other), cwd=self.tmp)
        (other / "remote.txt").write_text("r\n")
        self.r.git("add", "remote.txt", cwd=other)
        self.r.git("commit", "-q", "-m", "remote work", cwd=other)
        self.r.git("push", "-q", "origin", "main", cwd=other)
        self.r.write("local.txt", "l\n")
        self.r.git("add", "local.txt")
        self.r.git("commit", "-q", "-m", "local work")
        res = self.r.git("pull", "-q", "--no-rebase", "--no-edit", "origin2", "main", ok=False)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_17_second_worktree_keeps_the_first_guarded(self):
        wt = self.tmp / "wt2"
        self.r.git("worktree", "add", "-q", "-b", "game2", str(wt), "main")
        self.addCleanup(lambda: self.r.git("worktree", "remove", "--force", str(wt), ok=False))
        self.assertEqual(self.r.gate("--install", cwd=wt).returncode, 0)
        self.assertIn("✔ 관문 켜짐(main)", self.r.gate("--status").stdout)
        self.assertIn("✔ 관문 켜짐(game2)", self.r.gate("--status", cwd=wt).stdout)
        self.merge_blocked("worker/T-001-bad", "-m", "m", why="main still guarded after game2 install")


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mg-test-"))

    def tearDown(self):
        rmtree(self.tmp)

    def test_refuses_kit_not_committed(self):
        r = make_project(self.tmp / "p", commit_kit=False)
        res = r.gate("--install")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("커밋되지 않음", res.stdout)

    def test_refuses_quote_in_branch(self):
        r = make_project(self.tmp / "p")
        r.git("switch", "-q", "-c", "it's")
        self.assertNotEqual(r.gate("--install").returncode, 0)
        r.write("x.txt", "x\n")
        r.git("add", "x.txt")
        self.assertEqual(r.git("commit", "-q", "-m", "still fine", ok=False).returncode, 0)

    def test_relay_folder_mode(self):
        relay = self.tmp / "relay"
        relay.mkdir()
        with open(relay / "_dispatch", "w", newline="\n") as f:
            f.write(DISPATCH)
        os.chmod(relay / "_dispatch", 0o755)
        r = make_project(self.tmp / "p", hooks_path=relay)
        res = r.gate("--install")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertTrue((relay / "pre-merge-commit").exists())
        self.assertIn("✔ 관문 켜짐(main)", r.gate("--status").stdout)
        r.branch("worker/T-001-bad", BAD)
        res = r.git("merge", "worker/T-001-bad", "-m", "m", ok=False)
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("합치기 관문", res.stderr)
        r.git("merge", "--abort", ok=False)


class ScopeParseTest(unittest.TestCase):
    cfg = sc.load_config(None)

    def test_bold_nested_and_subheading_ban(self):
        card = ("## 만지는 파일\n\n- 고침: `a.mjs`\n- **고치지 않음**:\n  - `b.mjs`\n- 새로: `c/*.png`\n"
                "### 고치지 않음\n- `d.mjs`\n1. `e.mjs`\n")
        allow, ban, _, _ = sc.parse_card(card, {**self.cfg, "aliases": {}}, "")
        self.assertEqual(allow, ["a.mjs", "c/*.png"])
        self.assertEqual(ban, ["b.mjs", "d.mjs", "e.mjs"])

    def test_unreadable_banned_path_is_reported(self):
        _, ban, _, unread = sc.parse_card("## 만지는 파일\n- 고치지 않음: `src/{x}.mjs`\n", self.cfg, "")
        self.assertEqual(ban, [])
        self.assertIn("`src/{x}.mjs`", unread)

    def test_optional_extension_and_prefix(self):
        allow, *_ = sc.parse_card("## 만지는 파일\n- `game/m.glb(.mjs)`\n", self.cfg, "game/")
        self.assertEqual(allow, ["m.glb", "m.glb.mjs"])

    def test_heads(self):
        rep = "# R\n- 증거 파일(`.local/`, 직접 열어 봄)\n- 한 것\n```sh\n## 확인\n```\n~~~\n## 막힌 것\n~~~\n## 확인\n- 3 통과\n- 막힌 것 없이 끝남\n"
        heads = sc.heads_of(rep)
        self.assertTrue(any(h.startswith("증거") for h in heads))
        self.assertEqual(sum(h.startswith("확인") for h in heads), 1)
        self.assertFalse(any(h.startswith("막힌 것") for h in heads), "a body bullet is not a field")
        self.assertIn("3", sc.part(rep, r"^확인"))

    def test_glob_hit(self):
        self.assertTrue(sc.hit("assets/sign-*.png", "assets/sign-a.png"))
        self.assertFalse(sc.hit("assets/sign-*.png", "assets/x/sign-a.png"))
        self.assertTrue(sc.hit("b.mjs", "deep/dir/b.mjs"))
        self.assertTrue(sc.hit("lab/", "lab/x/y.html"))
        self.assertTrue(sc.hit("**/x.mjs", "x.mjs"))
        self.assertTrue(sc.hit("**/x.mjs", "a/b/x.mjs"))

    def test_mentions_is_whole_name(self):
        self.assertTrue(sc.mentions("고침: `src/a.js`.", "a.js"))
        self.assertFalse(sc.mentions("data.json 만", "a.js"))
        self.assertFalse(sc.mentions("xc.jsx", "c.js"))
        self.assertFalse(sc.mentions("unlocked.mjs", "locked.mjs"))


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    unittest.main(verbosity=1)
