"""Build the 'map went stale' repo: commit 1 is memo-board with a correct map, commit 2 changes the UI.

Usage: python setup_after_change.py <job dir>   (the runner has already copied fixtures/memo-board/ into it)
Commit 2 renames the add button and adds a sort control, so the map's 메모 추가 section and its
run mark are stale and a 정렬 feature is missing.
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import setup_repo  # noqa: E402

RENAME_OLD = '<button id="add-btn" disabled>추가</button>'
RENAME_NEW = '<button id="add-btn" disabled>메모 저장</button>'
SEARCH_OLD = """  <input id="search" type="search" placeholder="메모 검색 (/)" aria-label="메모 검색">
</section>"""
SEARCH_NEW = """  <input id="search" type="search" placeholder="메모 검색 (/)" aria-label="메모 검색">
  <select id="sort" aria-label="정렬">
    <option value="new">최신순</option>
    <option value="old">오래된순</option>
  </select>
</section>"""
REFRESH_OLD = """  const memos = await res.json();
  list.innerHTML = "";"""
REFRESH_NEW = """  const memos = await res.json();
  const newest = document.getElementById("sort").value === "new";
  memos.sort((a, b) => (b.pinned - a.pinned) || (newest ? b.id - a.id : a.id - b.id));
  list.innerHTML = "";"""
LISTENER_OLD = 'search.addEventListener("input", refresh);'
LISTENER_NEW = 'search.addEventListener("input", refresh);\ndocument.getElementById("sort").addEventListener("change", refresh);'


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


if __name__ == "__main__":
    target = Path(sys.argv[1])
    shutil.copy(HERE / "map-v1.md", target / "FEATURE_MAP.md")
    setup_repo.init(target)
    page = target / "static" / "index.html"
    html = page.read_text(encoding="utf-8")
    for old, new in ((RENAME_OLD, RENAME_NEW), (SEARCH_OLD, SEARCH_NEW), (REFRESH_OLD, REFRESH_NEW), (LISTENER_OLD, LISTENER_NEW)):
        if html.count(old) != 1:
            sys.exit(f"setup_after_change: expected one match for {old[:40]!r}")
        html = html.replace(old, new)
    page.write_text(html, encoding="utf-8")
    git("commit", "-q", "-am", "ui: rename add button to 메모 저장, add sort order", cwd=target)
