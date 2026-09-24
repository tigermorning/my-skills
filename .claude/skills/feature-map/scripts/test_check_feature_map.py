"""Self-test for check_feature_map.py. Run: python test_check_feature_map.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

HTML = '<button id="upload-btn">업로드</button><div data-testid="result-tab" class="tab-pane"></div>'

GOOD = """# Feature map
### 업로드
- 사용자 경로: 첫 화면 → "업로드"
- 선택자: `#upload-btn`, `[data-testid="result-tab"]`, `.tab-pane`
- 파일: `static/index.html`
- 검증: 버튼 클릭 → 결과 탭 표시
"""

CASES = [
    ("good map passes", GOOD, 0),
    ("missing file fails", GOOD.replace("static/index.html", "static/gone.html"), 1),
    ("unknown selector fails", GOOD.replace("#upload-btn", "#download-btn"), 1),
    ("missing 검증 line fails", GOOD.replace("- 검증: 버튼 클릭 → 결과 탭 표시\n", ""), 1),
    ("unverified entry is skipped", GOOD.replace("`#upload-btn`", "`#ghost` (미확인)"), 0),
]

if __name__ == "__main__":
    failed = 0
    for label, text, want in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "static").mkdir()
            (root / "static/index.html").write_text(HTML, encoding="utf-8")
            (root / "FEATURE_MAP.md").write_text(text, encoding="utf-8")
            r = subprocess.run([sys.executable, str(HERE / "check_feature_map.py"), str(root)], capture_output=True)
            if r.returncode != want:
                failed += 1
                print(f"FAIL {label}: exit {r.returncode}, want {want}\n{r.stdout.decode('utf-8', 'replace')}")
    print(f"{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)
