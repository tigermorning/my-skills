"""Self-test for check_feature_map.py. Run: python test_check_feature_map.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

HTML = '<button id="upload-btn">업로드</button><div data-testid="result-tab" class="tab-pane"></div><span>Compass</span>'
JSX = 'export function CompassStrip() { return <div className="strip">N</div> }\nfunction ResultPanel() {}'

GOOD = """# Feature map
## 실행 방법
- python -m http.server
## 시작 전제조건
- 서버가 떠 있음
## 조작 관례
- 끝 상태를 폴링한다
## 증거와 건너뜀 보고
- 관찰한 것만 적는다
## 기능
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
    ("line number in 파일 fails", GOOD.replace("`static/index.html`", "`static/index.html:12`"), 1),
    ("path::Symbol passes", GOOD.replace("`static/index.html`", "`static/index.html`, `src/Strip.tsx::CompassStrip`"), 0),
    ("unknown path::Symbol fails", GOOD.replace("`static/index.html`", "`src/Strip.tsx::MissingThing`"), 1),
    ("code identifier as selector fails", GOOD.replace("`.tab-pane`", "`CompassStrip`"), 1),
    ("visible text as selector passes", GOOD.replace("`.tab-pane`", "`Compass`"), 0),
    ("zero-width space fails", GOOD.replace("static/index.html", "static/​index.html"), 1),
    ("missing 시작 전제조건 section fails", GOOD.replace("## 시작 전제조건\n", ""), 1),
    ("missing 증거 section fails", GOOD.replace("## 증거와 건너뜀 보고\n", ""), 1),
]

if __name__ == "__main__":
    failed = 0
    for label, text, want in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "static").mkdir()
            (root / "static/index.html").write_text(HTML, encoding="utf-8")
            (root / "src").mkdir()
            (root / "src/Strip.tsx").write_text(JSX, encoding="utf-8")
            (root / "FEATURE_MAP.md").write_text(text, encoding="utf-8")
            r = subprocess.run([sys.executable, str(HERE / "check_feature_map.py"), str(root)], capture_output=True)
            if r.returncode != want:
                failed += 1
                print(f"FAIL {label}: exit {r.returncode}, want {want}\n{r.stdout.decode('utf-8', 'replace')}")
    print(f"{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)
