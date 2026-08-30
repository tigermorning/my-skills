---
name: project-kickoff
description: Before starting substantive work on a new project (or re-scoping an existing one with no documented PRD/MVP), gate all other work behind writing a PRD and defining the MVP slice first, then keep a fixed hygiene checklist running throughout the project (durable session log, PR-per-meaningful-unit, up-to-date README, secret hygiene, a definition of done tied to the PRD's success criteria). Applies regardless of language or domain; skip once the gate is already passed for a project, and skip heavier process (ADRs, issue trackers) for small solo projects. Also skip the gate entirely for a one-off technical spike/PoC whose deliverable is a single yes/no feasibility answer, not a product with users.
---

# Project Kickoff

새 프로젝트를 시작할 때 코드부터 짜지 마세요. PRD와 MVP 범위를 먼저 문서로
확정하고, 그 다음부터는 고정된 체크리스트를 프로젝트가 끝날 때까지 유지하세요.

## 왜 필요한가

- 급하게 코드부터 시작하면 "뭘 위해, 누구를 위해 만드는지"가 문서화되지 않은
  채로 진행되고, 나중에 범위가 계속 옆으로 번집니다(scope creep).
- 매 프로젝트마다 "이번엔 뭘 먼저 해야 하지"를 새로 판단하지 않도록, 순서와
  체크리스트를 고정해두면 잊지 않고 체계적으로 시작할 수 있습니다.
- 이 저장소의 다른 스킬([[durable-session-log]] 등)과 결합하면 프로젝트
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

4. **durable-session-log 적용**: `.claude/SESSION_LOG.md` + SessionStart
   hook. 세션마다 컨테이너가 새로 뜨는 원격 환경이면 필수, 로컬에 상시 남는
   환경이면 선택 — 자세한 절차는 [[durable-session-log]] 참고.
5. **의미 있는 작업 단위마다 브랜치 + PR**: 기능 하나, 버그 하나, 결정 하나
   단위로 쪼개서 만든다.
6. **README를 최신 상태로 유지**: 설치법·실행법이 실제 코드와 어긋나지
   않게 한다.
7. **시크릿 관리**: `.gitignore`에 자격증명/토큰류를 빠짐없이 넣고, 커밋 전에
   diff를 확인한다.
8. **완료의 정의를 PRD 성공 기준에 묶는다**: 최소한의 검증(자동 테스트든
   사람이 직접 확인하든) 없이 기능을 "완료"로 표시하지 않는다.

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

세션 간 맥락 유지는 [[durable-session-log]]를 참고하세요.
