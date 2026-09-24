---
name: feature-map
description: Write or update FEATURE_MAP.md for a project with a UI (web page, desktop GUI, TUI) — a file that tells an agent how to launch the app and how to reach each feature (screen path, shortcuts, selectors or widget names, source files, how to verify it works), so a vague bug report or screenshot can be mapped to code and reproduced without the human guiding the agent. Use when starting to work on an unfamiliar UI project, when asked to "make the agent able to find/verify features", when an agent keeps clicking around or guessing which file a UI bug lives in, and after adding or renaming a screen or feature. Includes a checker that fails when a listed file or selector no longer exists in the code.
---

# Feature Map

UI가 있는 프로젝트에 `FEATURE_MAP.md`를 만들어, 에이전트가 앱을 띄우고 각
기능까지 **스스로** 찾아가 검증할 수 있게 한다.

## 왜 필요한가

앱을 띄울 수 있게 해 줘도, 에이전트는 "왼쪽 사이드바가 느리다" 같은 보고를 받으면
그 기능이 코드 어디에 있는지, 화면에서 어떻게 가는지 몰라 헤맨다. 사람이 경로를
알려주는 동안 사람은 병목이 되고, 에이전트는 추측으로 엉뚱한 파일을 고친다.
기능별로 "가는 길"을 적어 두면 모호한 보고나 스크린샷만으로도 해당 코드와 재현
절차에 바로 도달한다. (Lauren Tan, Cursor — 검증 스킬의 핵심 부품으로 소개)

## 인식 신호

- UI가 있는 프로젝트인데 `FEATURE_MAP.md`가 없다.
- 에이전트가 UI 버그를 받고 코드를 읽지 않은 채 원인을 단정하거나, 화면을 무작정
  클릭하며 기능을 찾고 있다.
- 화면·라우트·버튼·단축키를 추가하거나 이름을 바꿨다 → 맵도 갱신하고 체커를 돌린다.
- 반대로 UI가 없는 라이브러리·CLI 전용 프로젝트는 대상이 아니다 (README의 명령
  목록이면 충분하다).

## 절차

1. **실행 방법부터 확인한다.** 실행 명령, 포트/URL, 필요한 환경변수(값은 적지
   않는다 — 이름만), 테스트 데이터 위치를 README·설정 파일·코드에서 찾아 적는다.
   가능하면 실제로 띄워서 확인한다. 못 띄웠으면 "미확인"이라고 적는다.
2. **조작 방법을 적는다.** 웹이면 브라우저 창(또는 CDP)으로 여는 URL, 데스크톱이면
   GUI 자동화 수단(Qt `objectName`, 접근성 이름, 단축키), 없으면 "수동 확인만 가능".
3. **기능을 코드에서 전수 수집한다.** 라우트, 템플릿, 버튼·메뉴 핸들러, 단축키
   바인딩, API 엔드포인트를 코드에서 찾는다. 기억이나 README만 믿지 않는다.
4. **기능마다 아래 형식으로 적는다.** 체커가 읽는 줄이므로 라벨을 그대로 쓴다.

   ```markdown
   ### <기능 이름>
   - 사용자 경로: 첫 화면 → "업로드" 버튼 → 결과 탭
   - 단축키: Ctrl+O (없으면 줄 생략)
   - 선택자: `#upload-btn`, `[data-testid="result-tab"]`
   - 파일: `static/index.html`, `app/routes/upload.py`
   - 검증: 샘플 `examples/a.srt` 업로드 → 결과 표에 행이 12개
   ```

   - `선택자`에는 **실행 중인 화면에서 찾을 수 있는 것만** 백틱으로 적는다. 웹이면
     id·class·`data-testid`·aria 속성·보이는 문구, 데스크톱이면 위젯 `objectName`·
     접근성 이름·보이는 버튼/메뉴 문구다. 보이는 문구는 코드의 문자열을 공백까지
     그대로 복사한다 (`"▶ ‖"`를 `"▶‖"`로 줄이면 못 찾는다). 여러 화면에서 같이 쓰는
     class라면 이 기능에만 있는 표식을 함께 적는다.
   - 컴포넌트 이름·함수 이름 같은 **코드 식별자는 선택자가 아니다.** 소스에는 있어도
     화면에는 없어서, 에이전트가 그걸로 요소를 찾으려다 헛걸음한다. 식별자는 `파일`
     줄에 `path::Symbol` 형태로 적는다.
   - `파일`에는 저장소 루트 기준 경로를 백틱으로 적는다. **줄 번호는 적지 않는다** —
     코드가 조금만 바뀌어도 틀린 정보가 된다. 위치는 `path::함수명`으로 가리킨다.
   - 사용자 경로에 "~에서 링크로 진입"처럼 적었다면 그 링크가 템플릿에 실제로 있는지
     확인한다. 없으면 "URL 직접 입력"이라고 적는다.
   - `검증`은 사람이 아니라 에이전트가 할 수 있는 확인이어야 한다
     (관찰할 값·개수·문구를 구체적으로).
5. **체커를 돌린다.** 적힌 파일이 존재하는지, 선택자 문자열이 소스에 있는지 검사한다.
   ```bash
   python <my-skills>/.claude/skills/feature-map/scripts/check_feature_map.py <프로젝트 루트>
   ```
   실패하면 맵을 코드에 맞게 고친다 — 맵에 맞춰 코드를 고치지 않는다.
6. **다른 에이전트에게 표본 검토를 맡긴다.** 체커는 "문자열이 있는가"만 본다.
   "그 파일·선택자가 정말 이 기능의 것인가"는 못 본다. 작성자가 아닌 에이전트에게
   무작위 3건 이상을 코드와 대조하게 한다. 기록 (2026-09-24, 7개 프로젝트):
   - 1차 작성 후 표본 21건 중 7건(33%)이 부분 오류.
   - 체커를 강화하고 전체를 감사한 뒤 새 표본 21건 중 6건(29%)이 부분 오류였다.
     파일·선택자 오류는 0건으로 줄었지만, `사용자 경로`·`검증` 문장의 사실 오류는
     그대로였다.
   - 그중 2건은 "실행해서 확인했다"고 적은 내용이 코드와 맞지 않았다.
7. **"실행 확인함"에는 관찰한 것을 그대로 적는다.** 본 문구·개수·응답 코드를 적고,
   못 본 것은 코드에서 추론했다고 밝힌다. 코드 분기와 어긋나는 관찰을 적었다면
   그 분기를 다시 확인한다. 추론을 관찰처럼 쓰면, 다음 에이전트는 가장 믿을 만한
   표시가 붙은 문장에서 속는다.
8. **맵 맨 위에 믿는 범위를 적는다.** 체커가 보장하는 것(파일·선택자)과 보장하지
   못하는 것(문장으로 쓴 사실)을 구분해서 적어, 읽는 에이전트가 맵을 맹신하지
   않게 한다.
9. **모르는 건 모른다고 적는다.** 코드로 확인 못 한 경로는 "(미확인)"을 붙인다.
   추측을 사실처럼 적은 맵은 에이전트를 더 멀리 잘못 보낸다.

## 하지 않는 것

- 시크릿·API 키 값·개인정보를 맵에 적지 않기 (환경변수 이름만)
- 맵을 만들면서 앱 코드를 고치지 않기 — 맵 작업은 문서 작업이다
- 체커를 통과시키려고 선택자를 느슨하게(예: `div`) 적지 않기

## 관련 스킬

맵으로 재현한 뒤 실제 입력으로 결과를 확인하는 단계는 [[real-world-review-cycle]].
