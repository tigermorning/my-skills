"""The feature-map graders must pass a correct map and fail each planted mistake on its own check.

Run: python scripts/skill-evals/test_feature_map_grader.py
"""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "feature-map/fixtures"
spec = importlib.util.spec_from_file_location("grade", HERE / "grade.py")
grade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grade)

RAN = [("Bash", {"command": "python app.py 8711 > /dev/null 2>&1 &"}), ("Bash", {"command": "curl -s http://127.0.0.1:8711/api/memos"})]
V2_EDITS = [
    ('- 사용자 경로: 첫 화면 → 메모 입력칸 → "추가" 버튼', '- 사용자 경로: 첫 화면 → 메모 입력칸 → "메모 저장" 버튼'),
    ("- 선택자: `#memo-input`, `#add-btn`, `추가`, `#status`", "- 선택자: `#memo-input`, `#add-btn`, `메모 저장`, `#status`"),
    ('- 검증: 입력칸이 비어 있으면 "추가"가 비활성이다.', '- 검증: 입력칸이 비어 있으면 "메모 저장"이 비활성이다.'),
    ("목록에 새 메모가 붙는다 (2026-09-01 실행 확인)", "목록에 새 메모가 붙는다 (2026-09-28 실행 확인)"),
]
SORT = "\n".join([
    "",
    "### 메모 정렬",
    "- 사용자 경로: 첫 화면 → 검색창 옆 정렬 목록",
    '- 선택자: `#sort`, `[aria-label="정렬"]`, `최신순`, `오래된순`',
    "- 파일: `static/index.html`",
    '- 검증: "오래된순"을 고르면 고정된 메모가 맨 위에 남고 나머지가 오래된 것부터 보인다 (2026-09-28 실행 확인).',
    "",
])
failures = []


def make(tmp, script):
    job = Path(tmp) / script.replace(".py", "")
    shutil.copytree(FIX / "memo-board", job)
    subprocess.run([sys.executable, str(FIX / script), str(job)], check=True, capture_output=True)
    return job


def failed(results):
    return {r["text"] for r in results if not r["passed"]}


def expect(label, results, want_failed):
    got = failed(results)
    want = {t for t in (r["text"] for r in results) if any(w in t for w in want_failed)}
    if got != want:
        failures.append(f"{label}: failed={sorted(got)} expected={sorted(want)}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        job = make(tmp, "setup_repo.py")
        shutil.copy(FIX / "map-v1.md", job / "FEATURE_MAP.md")
        expect("correct map, app run", grade.g_map_new(job, RAN), [])
        expect("marks without a run", grade.g_map_new(job, []), ["자기 포트로 띄우고", "실행 확인' 표시"])
        gold = (job / "FEATURE_MAP.md").read_text(encoding="utf-8")
        (job / "FEATURE_MAP.md").write_text(gold + "\n## 죽은 코드\n- `app.py::export_csv`는 정의만 있고 호출하는 곳이 없다.\n", encoding="utf-8")
        expect("unused export_csv flagged as dead", grade.g_map_new(job, RAN), [])
        (job / "FEATURE_MAP.md").write_text(gold + "\n### CSV 내보내기\n- 파일: `app.py::export_csv`\n- 검증: 메모가 CSV로 내려온다.\n", encoding="utf-8")
        expect("export_csv mapped as a feature", grade.g_map_new(job, RAN), ["export_csv"])
        (job / "FEATURE_MAP.md").write_text(gold, encoding="utf-8")
        page = job / "static/index.html"
        page.write_text(page.read_text(encoding="utf-8").replace('href="/settings"', 'href="/setting"'), encoding="utf-8")
        expect("app code changed", grade.g_map_new(job, RAN), ["앱 코드를 고치지 않음"])

        job2 = make(tmp, "setup_after_change.py")
        expect("map left stale", grade.g_map_update(job2, []), ["체커", "메모 저장", "정렬 기능", "2026-09-01"])
        text = (job2 / "FEATURE_MAP.md").read_text(encoding="utf-8")
        for old, new in V2_EDITS:
            assert text.count(old) == 1, old
            text = text.replace(old, new)
        (job2 / "FEATURE_MAP.md").write_text(text + SORT, encoding="utf-8")
        expect("correct update, app run", grade.g_map_update(job2, RAN), [])
        expect("new marks without a run", grade.g_map_update(job2, []), ["실행 확인' 표시"])
    for f in failures:
        print("FAIL", f)
    print(f"{8 - len(failures)}/8 passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
