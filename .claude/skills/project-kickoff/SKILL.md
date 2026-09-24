---
name: project-kickoff
description: Before starting substantive work on a new project (or re-scoping an existing one with no documented PRD/MVP), gate all other work behind writing a PRD and defining the MVP slice first, then keep a fixed hygiene checklist running throughout the project (cross-session memory via project-session-memory, PR-per-meaningful-unit, up-to-date README, secret hygiene, a definition of done tied to the PRD's success criteria). Applies regardless of language or domain; skip once the gate is already passed for a project, and skip heavier process (ADRs, issue trackers) for small solo projects. Also skip the gate entirely for a one-off technical spike/PoC whose deliverable is a single yes/no feasibility answer, not a product with users.
---

# Project Kickoff

새 프로젝트를 시작할 때 코드부터 짜지 마세요. PRD와 MVP 범위를 먼저 문서로
확정하고, 그 다음부터는 고정된 체크리스트를 프로젝트가 끝날 때까지 유지하세요.

## 왜 필요한가

- 급하게 코드부터 시작하면 "뭘 위해, 누구를 위해 만드는지"가 문서화되지 않은
  채로 진행되고, 나중에 범위가 계속 옆으로 번집니다(scope creep).
- 매 프로젝트마다 "이번엔 뭘 먼저 해야 하지"를 새로 판단하지 않도록, 순서와
  체크리스트를 고정해두면 잊지 않고 체계적으로 시작할 수 있습니다.
- 이 저장소의 다른 스킬([[project-session-memory]] 등)과 결합하면 프로젝트
  시작부터 세션 간 맥락 유지까지 하나의 일관된 워크플로우가 됩니다.

## 인식 신호 (다음 중 하나라도 해당하면 적용)

- 새 프로젝트를 막 시작하려는 시점이다 (저장소를 새로 만들거나, 첫 실질
  커밋 이전).
- 기존 프로젝트인데 PRD나 MVP 범위가 문서로 남아있지 않고, 이번에 방향을
  다시 크게 잡으려 한다.
- "일단 코드부터 짜보자"는 요청이 있었지만, 무엇을 왜 만드는지에 대한 합의된
  문서가 아직 없다.
- 반대로, 이미 PRD/MVP 정의가 끝난 프로젝트에서 다음 기능 하나를 더 얹는
  상황이면 이 게이트는 이미 통과한 것이므로 매번 다시 요구하지 않는다.
- 반대로, "이 기술/엔진이 이걸 지원하는가" 같은 예/아니오 하나만 확인하면
  끝나는 1회성 기술 스파이크·PoC라면 이 게이트를 아예 적용하지 않는다.
  대상 사용자·성공 기준 같은 PRD의 질문 자체가 이런 산출물에는 성립하지
  않는다 — README에 결과(PASS/FAIL)만 기록하면 충분하다.

## 절차

### 0단계 — 게이트: PRD와 MVP 없이는 다음 단계로 가지 않는다

1. **PRD 작성/확인**: 무엇을, 누구를 위해, 왜 만드는지와 성공 기준을 적는다
   (`PRD.md` 등 파일로 저장, git 커밋). 이미 있으면 이번 방향과 맞는지
   확인만 한다.
2. **MVP 범위 정의**: PRD 전체가 아니라 "가장 작은, 끝까지 도는 조각"만 따로
   추린다 (PRD 안의 별도 섹션이든 `MVP.md`든 상관없다). MVP 밖 기능은 MVP가
   끝나기 전까지 보류 목록으로만 남긴다.
3. 이 두 가지가 없는 채로 기능 구현에 들어가지 않는다. 사용자가 명시적으로
   스킵을 요청하면 그 요청을 따르되, 스킵했다는 사실 자체를 남긴다(예:
   SESSION_LOG 항목).

### 이후 상시 체크리스트 (프로젝트가 끝날 때까지 유지)

4. **project-session-memory 적용**: SessionStart/SessionEnd hook으로
   세션 간 맥락을 자동으로 이어간다. 세션마다 컨테이너가 새로 뜨는 원격
   환경이면 필수, 로컬에 상시 남는 환경이면 선택 — 자세한 절차는
   [[project-session-memory]] 참고.
5. **의미 있는 작업 단위마다 브랜치 + PR**: 기능 하나, 버그 하나, 결정 하나
   단위로 쪼개서 만든다.
6. **README를 최신 상태로 유지**: 설치법·실행법이 실제 코드와 어긋나지
   않게 한다.
7. **시크릿 관리**: `.gitignore`에 자격증명/토큰류를 빠짐없이 넣고, 커밋 전에
   diff를 확인한다.
8. **완료의 정의를 PRD 성공 기준에 묶는다**: 최소한의 검증(자동 테스트든
   사람이 직접 확인하든) 없이 기능을 "완료"로 표시하지 않는다.
9. **첫 기능을 만들기 전에 하드 가드레일을 건다**: 에이전트가 코드를 쓰는
   프로젝트라면 아래 "가드레일" 절을 따른다.

## 가드레일 (에이전트가 코드를 쓰는 프로젝트, 첫 기능 전에)

가드레일 없이 빠르게 만든 프로토타입은 에이전트가 **가장 편한 방법**으로 문제를 풀어서,
시간이 지나면 아무도 이해하지 못하는 지름길 덩어리가 된다. 새 프로젝트가 가장 위험한
이유는 이때 가드레일이 하나도 없기 때문이고, 가장 큰 기회인 이유는 지금이 가드레일을 걸
가장 싼 시점이기 때문이다. (근거: `~/.claude/references/agent-trust-lauren-tan.md` 7~9부)

에이전트는 가까운 패턴을 베끼고, 열려 있는 파일에 끼워 넣고, 컴파일만 되면 가장 짧은 길을
고른다. 이 버릇을 프롬프트로 고치려 하지 말고, **가장 쉬운 길이 곧 올바른 길이 되게** 구조를
정한다.

1. **구조 규칙 하나**: 기능 하나 = 디렉토리 하나, 새 기능은 공유 파일에 분기를 넣지 않고
   자기 폴더에 파일을 더하는 방식으로 끝나게 한다. 파일 이름까지 정해 두면 베낄 패턴이
   하나뿐이라 고민할 게 없다.
2. **기계가 막는 검사 하나**: 금지된 의존성·패턴은 부탁이 아니라 CI 실패로 막는다.
   ```bash
   python <my-skills>/.claude/skills/project-kickoff/scripts/check_boundaries.py
   ```
   - 프로젝트 루트의 `guardrails.json`에 규칙을 적는다. 규칙마다 **대신 무엇을 쓸지**를 반드시
     적는다 (스크립트가 없으면 규칙을 거부한다). 금지만 알려 주면 에이전트는 다음 지름길을 찾는다.
   - 언어의 린터·타입 검사·컴파일러가 있으면 그것을 같은 CI 명령에 묶는다.
   - 로컬은 pre-commit, 원격은 CI에서 같은 명령을 돌린다.
3. **자주 터지는 함정은 목록으로**: 그 스택에서 에이전트가 반복해서 만드는 문제(예: React의
   `useEffect`)를 금지 규칙으로 옮긴다. 처음에는 비어 있어도 되고, 아래 4번으로 자란다.
4. **리뷰 코멘트는 검사로 승격한다**: 같은 지적을 두 번 하게 되면 그것은 코드 스멜이다.
   "사람이 PR에 코멘트를 다는 대신, 이걸 CI 실패로 바꾸거나 범주째 없앨 수 없나"를 묻고
   `guardrails.json`에 규칙을 추가한다. 사람이 읽고 강제하는 상태(코드 리뷰 랜드)가 가장 나쁘다.
5. **주석에는 이유만**: 날짜·"누가 말했다"·지난 일은 코드 주석이 아니라 커밋 메시지에 둔다.
   `guardrails.json`의 `comments.no_history`가 이걸 검사한다.
6. **강제 수단은 겹쳐서, 하드가 먼저**: (1) 코드베이스 구조 (2) 정적 분석·CI·컴파일러 (3) 룰 파일
   (4) 스킬 (5) 스타일 가이드. 앞의 둘이 하드이고 뒤의 셋은 에이전트가 잊는다. 뒤의 셋만 있으면
   코드베이스가 망가지는 건 시간문제다. 가능하면 컴파일러가 많은 걸 강제하는 스택을 고른다.
7. **UI가 있으면 검증 수단도 같이**: 앱을 띄워 조작하는 방법은 [[feature-map]]으로 적고,
   "됐다"고 말하기 전에 [[verify-by-running]]으로 실제로 돌려 본다.

작은 개인 프로젝트에서는 1번과 2번의 최소 버전(폴더 규칙 한 줄과 `check_boundaries.py` 한 규칙)만
두고, 3~6번은 필요해질 때 추가한다. 코드를 에이전트가 쓰지 않는 프로젝트에는 이 절을 적용하지 않는다.

## 규모에 따라 생략 가능한 것

- ADR(결정 기록 전용 문서), 별도 이슈 트래커 같은 무거운 프로세스는 협업자가
  늘거나 프로젝트가 커졌을 때만 추가한다. 작은 개인 프로젝트에 처음부터
  강제하지 않는다.

## 하지 않는 것

- PRD/MVP 정의 없이 바로 기능 구현부터 시작하지 않기.
- MVP 범위 밖 기능을 "일단 만들어보고 싶어서" 먼저 만들지 않기 — 보류
  목록에 적어두고 MVP 완료 후로 미룬다.
- 작은 프로젝트에 ADR·이슈 트래커 같은 무거운 프로세스를 처음부터 강제하지
  않기.

## 실제 적용 사례

이 스킬을 만든 뒤 실제 프로젝트 4곳(`subtitle-tc-generator`,
`who-ate-my-cheesecake`, `spum-maze-poc`, `korean-subtitle-corrector`)에
대조해봤는데, 전부 게이트가 필요 없는 경우였다: 두 곳은 이미 `PRD.md`/
`PRD_LOCKED_PRINCIPLES.md`가 있었고, 한 곳(`spum-maze-poc`)은 "SPUM 엔진이
걸어다닐 수 있는 공간을 지원하는가"만 확인하고 끝난 1회성 기술 스파이크라
PRD 질문(대상 사용자·성공 기준) 자체가 성립하지 않았다. 이 마지막 사례가
위 "1회성 기술 스파이크·PoC는 제외" 조항의 근거다 — 실제로 대조해보기 전엔
이 예외가 문서에 없었다.

## 관련 스킬

세션 간 맥락 유지는 [[project-session-memory]]를 참고하세요.
