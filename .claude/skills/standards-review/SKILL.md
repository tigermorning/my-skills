---
name: standards-review
description: Enforce coding standards in a separate review pass, not in the implementer's prompt. After an agent (or you) finishes a change and before it goes to a PR, merge or human review, spawn a reviewer sub-agent with its own context that reads the diff, the task/spec and the repo's CODING_STANDARDS.md, catches tests that lie (tautological, source-text, unfailable mocks), and by default fixes what it finds in its own commit instead of leaving comments. Also use when setting up coding standards for an agent-driven repo, when AGENTS.md/CLAUDE.md is bloated with style rules, or when agent PRs pass CI but keep needing the same human comments. Skip for one-line, config or typo changes.
---

# Standards Review — 규칙은 구현자가 아니라 리뷰어가 집행한다

구현 에이전트는 한 컨텍스트에서 탐색·수정·디버깅을 다 해야 해서 이미 과부하다.
여기에 코딩 규칙까지 얹으면 규칙도 구현도 같이 나빠진다.
리뷰 에이전트는 diff를 받고 조금 탐색할 뿐 구현·디버깅이 없어 여유가 있다.
그래서 규칙은 리뷰어에게 몰아준다.

- 구현 = 되게 만들기 (red → green)
- 리뷰 = 좋게 만들기 (refactor, 다른 컨텍스트에서)

출처: Matt Pocock, "Fixing the PR Bottleneck"(AI Engineer Paris 2026)의 원칙을 일반화.

## 인식 신호

- 에이전트가 만든 변경을 PR·merge·사람 리뷰로 넘기기 직전.
- 사람 리뷰에서 같은 종류의 지적(이름, 구조, 테스트 방식)이 계속 나온다.
- CI는 초록인데 머지하기 불안하다.
- `AGENTS.md`/`CLAUDE.md`에 스타일·설계 규칙이 길게 쌓여 있다.
- 새 저장소에 에이전트용 코딩 규칙을 처음 정한다.

해당 없음: 한 줄 수정, 설정값 변경, 문서 오타. 리뷰 패스 비용이 더 크다.

## 규칙은 두 층

| 층 | 파일 | 무엇 | 언제 만드나 |
|---|---|---|---|
| 사용자 공통 | `$REVIEW_STANDARDS` → `~/.claude/REVIEW_STANDARDS.md` → `~/.claude/references/review-standards.md` (먼저 찾은 것) | 어느 프로젝트에서나 반복되는 판단 규칙, 나에게 위험한 변경(one-way) 목록 | 한 번. 회고에서 여러 프로젝트에 같은 지적이 나오면 더함 |
| 프로젝트 | 저장소 루트 `CODING_STANDARDS.md` | 그 저장소에서만 통하는 기준 | 미리 만들지 않음. 그 저장소에서 같은 지적이 두 번 나오면 |

- 리뷰어는 둘 다 읽는다. 서로 다르면 **프로젝트 규칙이 이긴다**.
- 프로젝트마다 다 따로 만들 필요는 없다. 공통 파일 하나로 시작하고, 프로젝트 파일은 [[review-retro]]가 필요할 때만 늘린다.
- 프로젝트 전용 스킬이 이미 규칙을 담고 있으면(예: 블로그 글쓰기 스킬) 그것이 프로젝트 층이다.

## 준비 (저장소당 한 번 — 필요해졌을 때)

1. 저장소 루트에 `CODING_STANDARDS.md`를 둔다.
   - 판단이 필요한 규칙만 적는다. 예: "테스트는 공개 인터페이스에서", "모듈은 깊게".
   - 기계로 잡을 수 있는 규칙은 여기 쓰지 말고 린트·훅·CI로 만든다.
     (경계 검사는 [[project-kickoff]]의 `check_boundaries.py`, 일꾼 범위는 [[worker-merge-gate]])
   - 아무도 안 읽던 설계 문서가 있으면 요점을 여기로 옮긴다.
2. 전역 지시 파일(`AGENTS.md`, `CLAUDE.md`)에서 스타일·설계 규칙을 빼고,
   "코딩 규칙은 `CODING_STANDARDS.md`, 리뷰 패스에서 집행"이라는 한 줄 포인터만 남긴다.
3. 팀 공용 어휘를 정해 두면 리뷰 지적이 짧아진다.
   - locality: 한 변경이 한곳에 모이는가
   - leverage: 호출하는 쪽이 작은 인터페이스로 얻는 가치
   - seam: 구현을 갈아 끼울 수 있는 이음매

## 절차

1. **입력 모으기**
   - 먼저 구현자가 커밋했는지, `git status --short`가 비었는지 본다.
     커밋 안 한 변경이 있으면 구현자에게 커밋을 받는다. 리뷰 커밋에 구현자 변경이 섞이면 누가 무엇을 바꿨는지 가를 수 없다.
   - diff: 기준점(브랜치 분기점·`main`·카드 시작 커밋)부터 `HEAD`까지.
   - 스펙: 이슈·카드·PRD의 해당 부분.
   - 사용자 공통 규칙 파일(있으면)과 저장소 `CODING_STANDARDS.md`(있으면). 둘 다 없으면 아래 3번 목록만으로 본다.
2. **리뷰어를 하위 에이전트로 띄운다** (구현한 컨텍스트에서 직접 리뷰하지 않는다).
   - 두 축을 나눠 본다. 크면 하위 에이전트 둘로 병렬.
     - Standards: 저장소 규칙을 지켰나.
     - Spec: 스펙을 빠짐없이, 넘치지 않게 구현했나.
   - 리뷰어는 diff 주변을 조금 탐색해도 되지만 새 기능을 만들지 않는다.
3. **테스트 거짓말 탐지** (CI 초록을 믿지 않는다)
   - 되받아쓰기: 구현의 상수·분기를 그대로 단언한다. 예: `LIMIT = 280` 옆에 `expect(LIMIT).toBe(280)`.
   - 소스 텍스트 검사: 렌더·실행 대신 소스 파일을 문자열로 읽어 순서·포함 여부를 본다.
   - 실패할 수 없는 테스트: 실패 모드가 있는 실제 의존성을 가짜로 바꿔 오류 경로가 사라졌다.
   - 내부 찌르기: 공개 인터페이스 대신 private 함수·내부 상태를 직접 검사한다.
   - 처방은 "테스트를 지운다"가 아니라 "인터페이스에서 동작을 검사하게 고친다".
     인터페이스가 너무 얕아 그렇게 못 하면 모듈을 깊게 만드는 리팩터를 제안한다.
4. **기본 동작은 고쳐서 커밋**
   - 확실한 위반은 리뷰어가 직접 고치고 별도 커밋으로 남긴다. 메시지 예: `review: test through public API`.
   - 고친 뒤 빠른 검사를 다시 돌린다. 깨지면 되돌리고 댓글로 남긴다.
   - 일꾼 브랜치(카드 하나짜리)에서는 카드의 "만지는 파일" 안만 고친다.
     카드 밖 파일을 고쳐야 하면 고치지 말고 보고서 "합칠 때 주의" 칸에 경로와 이유를 적는다.
     [[worker-merge-gate]]가 카드 밖 수정을 그 칸으로 판정하므로, 리뷰 커밋도 같은 범위를 지킨다.
   - 댓글(보고)로 남기는 것은 셋뿐:
     - 스펙 해석이 갈리는 것
     - 동작이 바뀌는 큰 리팩터
     - 확신이 없는 것
   - 댓글만 잔뜩 다는 리뷰는 사람의 일을 늘린다.
5. **보고**
   - `## Standards` / `## Spec` 두 절.
   - 각 절: 고친 것(커밋 해시) → 남긴 질문 → 축별 건수.
   - 같은 지적이 이번에도 나왔으면 "반복"이라고 표시한다 → [[review-retro]] 후보.

## 하지 않는 것

- 구현 에이전트 프롬프트에 `CODING_STANDARDS.md` 전문을 넣지 않는다.
- 리뷰어가 스펙 밖 기능을 추가하지 않는다.
- 범용 외부 리뷰 봇만으로 대신하지 않는다. 범용은 오탐이 많거나, 특정 언어에 묶인다.
  보조로 쓰는 건 괜찮다.
- 같은 컨텍스트에서 구현하고 스스로 승인하지 않는다.

## 다른 스킬과의 관계

- [[verify-by-running]]: 리뷰 전에 실제로 돌려 본 증거가 있어야 Spec 축을 판단할 수 있다.
- [[pr-merge-danger]]: 리뷰가 끝난 변경을 사람에게 넘길 때 본문 형식과 위험도.
- [[review-retro]]: 리뷰에서 반복된 지적을 검사·규칙으로 옮긴다.
