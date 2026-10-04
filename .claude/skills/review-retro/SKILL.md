---
name: review-retro
description: Retrospective that turns human feedback into guards so the same review comment is never written twice. Feed it one agent session, a PR plus its session, or the last week of merged PRs and sessions; it collects what the human corrected, finds remarks made more than once (bundled collect_feedback.py reads gh PR reviews and Claude Code transcripts), and proposes, in severity order, where each lesson should live - automated check (lint, hook, CI, merge gate) first, CODING_STANDARDS.md only for judgment calls, a pointer in AGENTS.md/CLAUDE.md when the agent could not find something, a cheaper tool when calls were wasteful, and deletions when steering files or skills are bloated or have no effect. Suggests only; applies changes after the user approves. Use at the end of a work unit, weekly, after a painful review, or when the user says they keep repeating themselves.
---

# Review Retro — 같은 지적을 두 번 쓰지 않기

사람 리뷰는 코드만 보는 일이 아니다. 그 코드를 만든 시스템(지시 파일, 스킬, 검사, 도구)을 보는 일이다.
같은 지적을 두 PR에서 했다면, 첫 번째 지적이 시스템에 남지 않은 것이다.
이 스킬은 지적을 모아 "다음에는 기계가 막게" 바꾸는 후보를 낸다.
오늘의 리뷰가 다음 리뷰를 가볍게 만드는 복리 구조다.

출처: Matt Pocock, "Fixing the PR Bottleneck"(AI Engineer Paris 2026)의 retro 원칙과
공개 `retro` 스킬의 점검 분류를 일반화.

## 인식 신호

- 작업 단위(카드, 마일스톤, PR 묶음)를 마쳤다.
- 주 1회 정기 회고.
- 사용자가 "또 이러네", "전에 말했잖아", "몇 번째야"라고 했다.
- 리뷰가 유난히 길고 고통스러웠다.
- 에이전트가 같은 파일을 찾느라 매번 헤맨다.

## 입력 (하나 이상)

- 에이전트 세션 하나 (현재 세션 또는 지정한 transcript)
- PR 하나 + 그 PR을 만든 세션
- 기간: 지난 N일의 머지된 PR 리뷰 + 세션들

수집기:

```bash
python scripts/collect_feedback.py --gh-repo OWNER/REPO --days 7
```

```bash
python scripts/collect_feedback.py --transcripts ~/.claude/projects/<프로젝트 폴더> --days 7
```

- `--transcripts`는 세션 파일 하나(`*.jsonl`)나 폴더를 받는다. 기간은 메시지마다 `timestamp`로 거른다.
- 사람이 쓴 리뷰·댓글·지시만 모은다.
  - 세션 기록: 이벤트에 `origin.kind`가 있으면 `human`만 남긴다. 없으면 블록마다 태그로 시작하는 것(시스템 알림·예약 작업)을 뺀다. 압축 요약·도구 결과·"좋아요" 같은 짧은 말도 뺀다.
  - GitHub: 봇(`type: Bot`, 로그인 끝 `[bot]`)은 뺀다. 봇 표시가 없는 자동 계정은 `--exclude-author LOGIN`으로 뺀다.
  - 머지된 PR은 200개까지만 읽는다. 넘으면 경고가 나온다 — `--days`를 줄인다.
- 단어가 많이 겹치는 지적을 묶어 두 목록으로 낸다. A~B, B~C가 비슷하면 A·B·C가 한 묶음이다.
  - 서로 다른 PR·세션에 걸친 "반복 후보"
  - 한 세션·PR 안에서 다시 한 말("같은 세션에서 또")
- 단어 겹침이라 후보일 뿐이다. 표현이 다른 같은 지적은 못 묶는다. 같은 교훈인지는 사람이나 에이전트가 판단한다.
- `gh`가 없거나 경로가 없으면 종료 코드 2.
- 셀프 테스트: `python scripts/test_collect_feedback.py`

## 점검 분류

| 분류 | 묻는 것 | 보통 옮길 곳 |
|---|---|---|
| 자동 검사 | 기계가 잡을 수 있었나? | 린트 규칙, pre-commit 훅, CI, merge 관문 |
| 코딩 규칙 | 판단이 필요한 기준인가? | `CODING_STANDARDS.md` (리뷰 패스에서 집행 — [[standards-review]]) |
| 탐색 | 에이전트가 정보를 쉽게 찾았나? 숨은 의존이 있었나? | `AGENTS.md`/`CLAUDE.md`의 짧은 포인터, 지도 문서([[feature-map]]) |
| 정보 접근 | 필요한데 없던 정보가 있었나? | 문서·스크립트 추가, 접근 권한 |
| 도구 경제성 | 비싸거나 토큰을 많이 쓰는 호출이 있었나? | 더 좁은 명령, 스크립트, 캐시 |
| 비대함 | 전역 지시 파일·스킬이 길어 묻히거나 서로 부딪히나? | 줄이기, 쪼개기, 오래된 상태 줄 지우기 |
| 효과 없음 | 있어도 행동이 안 바뀌는 지시가 있나? | 지우기, 또는 하드 가드로 바꾸기 |
| 리뷰 강도 | two-way로 보고 건너뛴 변경이 사고를 냈나? | [[pr-merge-danger]] 기준 고치기 |

## 절차

1. **모으기**: 수집기를 돌리거나, 세션·PR을 직접 읽어 사람이 고친 것을 목록으로 만든다.
2. **묶기**: 같은 교훈끼리 묶는다. 반복된 것에 표시한다.
3. **분류**: 위 표로 분류한다. 한 교훈에 한 분류.
4. **옮길 곳 고르기** — 강한 것부터:
   1. 기계가 막는다(훅·CI·관문). 에러 메시지에 올바른 대안을 적는다.
   2. 리뷰 패스가 집행한다(`CODING_STANDARDS.md`).
   3. 포인터 한 줄(전역 지시 파일).
   4. 지운다(효과 없는 지시, 오래된 상태).
   - 전역 지시 파일에 규칙을 늘리는 것은 마지막 수단이다. 구현 에이전트의 컨텍스트를 잡아먹는다.
5. **보고**: 심각도 순서 후보 목록. 후보마다:
   - 증상: 근거(PR·세션 위치와 짧은 인용)
   - 분류
   - 제안: 무엇을 어디에 (파일 경로)
   - 비용: 만드는 데 드는 일, 오탐 위험
6. **적용은 승인 후**: 사용자가 고른 것만 반영한다.
   - 스킬을 고쳤으면 그 스킬의 eval을 다시 돌린다.
   - 검사를 새로 만들었으면 지난 사례에 되짚어 오탐을 본다(예: [[worker-merge-gate]]의 `--retro`).

## 하지 않는 것

- 승인 없이 지시 파일·스킬·검사를 고치지 않는다.
- 한 번 나온 지적을 바로 규칙으로 만들지 않는다. 두 번째부터 후보, 단 one-way 사고는 한 번이면 충분하다.
- "주의하자" 같은 다짐을 결과로 내지 않는다. 옮길 곳이 없는 교훈은 기록만 한다.
- 개인 정보·비공개 자료가 든 transcript를 밖으로 보내지 않는다. 수집 결과는 로컬에만 둔다.
