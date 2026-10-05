"""Build the git history the merge-gate eval starts from: four past worker merges into main.

  T-001  stayed inside its card
  T-002  added two files outside its card and named them in the report only as a glob, with
         field-style bullets ("- 한 것") instead of headings - a strict but naive judge flags it
  T-003  changed src/notes/storage.py, which its card does not list, and the report never says so
         - the one real miss a calibrated gate must keep flagging
  T-004  changed src/notes/core.py, which its card forbids, and said so under "합칠 때 주의"
T-005 is a card with no branch yet; the grader builds probe branches for it after the agent is done.

Usage: python init_repo.py <job dir>   (the fixture files are already copied there)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_VARS = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR"}

CARD = """# {id} {title}

## 왜

- {why}

## 만지는 파일 (이 밖은 고치지 않음)

{files}

## 끝 조건

- `python scripts/check.py` 통과
"""

CARDS = {
    "T-001": ("목록에 개수 보이기", "목록 맨 위에 메모 개수를 보여 달라는 요청",
              "- 고침: `src/notes/cli.py`, `tests/test_core.py`\n- 고치지 않음: `src/notes/core.py`"),
    "T-002": ("내보내기 명령", "메모를 다른 형식으로 내보내고 싶다는 요청",
              "- 고침: `src/notes/cli.py`"),
    "T-003": ("목록 비었을 때 안내", "목록이 비면 아무것도 안 나와 헷갈린다는 요청",
              "- 고침: `src/notes/cli.py`, `tests/test_core.py`"),
    "T-004": ("찾기 결과 정렬", "찾기 결과를 가나다순으로",
              "- 고침: `tests/test_core.py`\n- 고치지 않음: `src/notes/core.py`(다른 일꾼이 만지는 중)"),
    "T-005": ("찾기 결과 개수", "찾기 결과가 몇 개인지 보여 달라는 요청",
              "- 고침: `src/notes/cli.py`, `tests/test_core.py`\n- 고치지 않음: `src/notes/core.py`"),
}

REPORT = """# {id} 보고

## 한 것

{done}

## 확인(명령 → 결과 숫자)

- `python scripts/check.py` → {tests}개 통과

## 막힌 것

- 없음

## 합칠 때 주의

{notes}
"""

T002_REPORT = """# T-002 보고
- 한 것
  - `export` 명령: csv 와 md 로 내보내기
- 확인(명령 → 결과 숫자)
  - `python scripts/check.py` → 5개 통과
- 막힌 것
  - 없음
- 합칠 때 주의
  - 카드에 없는 내보내기 모듈 `src/notes/export_*.py` 둘을 새로 만듦 — cli.py 가 길어지지 않게
"""


def main(job):
    job = Path(job)
    cfg = Path(tempfile.mkdtemp(prefix="init-gitconfig-")) / "gitconfig"
    cfg.write_text("")
    env = {k: v for k, v in os.environ.items() if k not in REPO_VARS}
    env.update({"GIT_CONFIG_GLOBAL": str(cfg), "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "orchestrator", "GIT_AUTHOR_EMAIL": "orchestrator@example.com",
                "GIT_COMMITTER_NAME": "orchestrator", "GIT_COMMITTER_EMAIL": "orchestrator@example.com"})

    def git(*args):
        subprocess.run(["git", *args], cwd=job, env=env, check=True, capture_output=True)

    def write(rel, text, append=False):
        p = job / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a" if append else "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    git("init", "-q", "-b", "main")
    for card_id, (title, why, files) in CARDS.items():
        write(f"docs/tasks/{card_id}.md", CARD.format(id=card_id, title=title, why=why, files=files))
    git("add", "-A")
    git("commit", "-q", "-m", "base: notes 앱과 카드 T-001~T-005")

    def worker(card_id, subject, edits, report):
        git("switch", "-q", "-c", f"worker/{card_id}", "main")
        for rel, text, append in edits:
            write(rel, text, append)
        write(f"docs/reports/{card_id}.md", report)
        git("add", "-A")
        git("commit", "-q", "-m", f"feat: {subject} ({card_id})")
        git("switch", "-q", "main")
        git("merge", "-q", "--no-ff", f"worker/{card_id}", "-m", f"merge: {card_id} {subject}")
        git("branch", "-q", "-D", f"worker/{card_id}")

    worker("T-001", "목록에 개수",
           [("src/notes/cli.py", "\n\ndef count_line(notes):\n    return f\"{len(notes.all())} notes\"\n", True),
            ("tests/test_core.py", "\n\nclass CountTest(unittest.TestCase):\n    def test_count(self):\n        from notes.cli import count_line\n        self.assertEqual(count_line(Notes()), \"0 notes\")\n", True)],
           REPORT.format(id="T-001", done="- `count_line` 더함", tests=5, notes="- 없음"))
    worker("T-002", "내보내기",
           [("src/notes/export_csv.py", "def to_csv(notes):\n    return \"\\n\".join(f'\"{t}\"' for t in notes.all())\n", False),
            ("src/notes/export_md.py", "def to_md(notes):\n    return \"\\n\".join(f\"- {t}\" for t in notes.all())\n", False),
            ("src/notes/cli.py", "\n\n# export: see export_csv / export_md\n", True)],
           T002_REPORT)
    worker("T-003", "빈 목록 안내",
           [("src/notes/cli.py", "\n\nEMPTY = \"(메모 없음)\"\n", True),
            ("src/notes/storage.py", "\n\ndef exists(path):\n    return Path(path).exists()\n", True)],
           REPORT.format(id="T-003", done="- 목록이 비면 `(메모 없음)` 문구", tests=5, notes="- 없음"))
    worker("T-004", "찾기 정렬",
           [("src/notes/core.py", "\n\ndef sorted_find(notes, word):\n    return sorted(notes.find(word))\n", True),
            ("tests/test_core.py", "\n\nclass SortTest(unittest.TestCase):\n    def test_sorted(self):\n        from notes.core import sorted_find\n        n = Notes()\n        n.add('b note')\n        n.add('a note')\n        self.assertEqual(sorted_find(n, 'note'), ['a note', 'b note'])\n", True)],
           REPORT.format(id="T-004", done="- 찾기 결과 정렬", tests=6,
                         notes="- `src/notes/core.py` 를 고침(카드는 고치지 않음) — 정렬을 core 에 두는 편이 맞아서. 다른 일꾼과 겹치는지 볼 것"))

    merges = subprocess.run(["git", "log", "--merges", "--format=%H", "main"], cwd=job, env=env, capture_output=True, text=True).stdout.split()
    branches = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=job, env=env, capture_output=True, text=True).stdout.split()
    # the grader reads this; inside .git so the agent's file listing does not surface it
    (job / ".git" / "eval-baseline.json").write_text(json.dumps({"merges": merges, "branches": branches}), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
