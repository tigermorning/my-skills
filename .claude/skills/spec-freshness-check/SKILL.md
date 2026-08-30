---
name: spec-freshness-check
description: When a project's correctness depends on an external spec that can change independently of the codebase (a regulation, a style guide, a third-party API version/schema, a legal/tax rule set), check at the start of a session — before relying on cached knowledge of it — whether that spec has been amended since it was last verified, using its authoritative source. Record the check date and outcome so the next check knows the baseline.
---

# Spec Freshness Check

외부 규정/스펙에 의존하는 프로젝트에서는, 세션을 시작할 때 그 스펙이
마지막 확인 이후 개정됐는지부터 확인하세요. 확인 없이 예전에 알던 내용을
그대로 전제하지 마세요.

## 왜 필요한가

`korean-subtitle-corrector`는 국립국어원 어문 규정에 의존하는데, 이 규정은
프로젝트 코드와 무관하게 개정될 수 있습니다. 세션 시작 시점에 "지난번에
확인한 규정이 아직 유효한가"를 확인하지 않으면, 이미 개정된 낡은 규정을
근거로 계속 판단하게 됩니다 — 이건 코드 버그가 아니라 "세상이 바뀐 걸
모르고 있는" 문제라서 코드 리뷰로는 절대 안 잡힙니다. 이 패턴을 프로젝트
하나에만 묶어두지 않고, 외부 권위 있는 근거에 의존하는 모든 프로젝트에
적용할 수 있게 일반화합니다.

## 인식 신호 (다음 중 하나라도 해당하면 적용)

- 프로젝트의 정확성이 코드 자체가 아니라 외부의 권위 있는 근거(법령,
  공식 규정, 스타일 가이드, 표준, 세율표)에 달려 있다 — 그리고 그 근거는
  프로젝트 배포 주기와 무관하게 바뀔 수 있다.
- 특정 외부 API의 버전/스키마/요금 정책에 맞춰 동작이 짜여 있고, 그
  API 제공자가 사전 통보 없이 바꿀 수 있다.
- 마지막으로 그 근거를 확인한 날짜가 기록돼 있지 않거나, 기록된 날짜가
  오래됐다 (세션 시작 시점마다 재확인 안 하고 있었다는 신호).
- 반대로, 근거가 프로젝트 자체 코드/문서로 완결되어 외부에 의존하지
  않는다면 이 절차는 불필요하다.

## 구체적 사례 (이 스킬이 태어난 실제 사고)

`korean-subtitle-corrector` 프로젝트의 `session-start-regulation-check`
스킬이 원형이다 — 국립국어원 어문 규정이 세션 시작 시점 기준으로
개정됐는지 확인하는 프로젝트 전용 스킬이었다. 같은 패턴("외부 근거 이름"만
바꾸면 재사용 가능)이 README의 프로젝트 전용 카탈로그에 이미 일반화
아이디어로 기록돼 있었고, 이번에 실제로 범용 스킬로 승격했다.

## 절차

1. **의존 대상 식별**: 프로젝트가 의존하는 외부 근거(법령명, 규정명,
   API 이름+버전, 표준 문서 등)와 그 권위 있는 출처(공식 사이트, API
   changelog, 법령 정보 사이트)를 명시적으로 나열한다.
2. **마지막 확인일 조회**: 각 근거별로 "마지막으로 확인한 날짜와 그때의
   내용"을 프로젝트 기록(README, CLAUDE.md, 또는 별도 파일)에서 찾는다.
   기록이 없으면 "한 번도 확인 안 됨"으로 간주한다.
3. **최신 여부 확인**: 세션 시작 시점(또는 그 근거를 다시 쓰기 직전)에
   출처를 다시 조회해 마지막 확인 이후 바뀐 게 있는지 대조한다.
4. **변경 발견 시**: 변경 사항을 코드/판단 로직에 반영하고, 영향받는
   기존 결과물(테스트 픽스처, 이미 처리된 결과 등)도 재검토가 필요한지
   확인한다.
5. **기록 갱신**: 확인 날짜와 결과(변경 없음 / 이런 부분이 바뀜)를
   기록에 즉시 남긴다. 다음 세션이 이 기록을 baseline으로 쓴다.

## 하지 않는 것

- 마지막 확인일 기록 없이 "예전에 확인했으니 됐다"고 넘어가지 않기
- 변경을 발견하고도 영향받는 기존 산출물 재검토를 생략하지 않기
- 근거 자체가 프로젝트 코드로 완결된 경우까지 이 절차를 적용하지 않기
  (불필요한 오버헤드)

## 관련 스킬

예외 있는 규칙을 코드화할 때 정답표를 만드는 절차는 [[verify-then-code]]를
참고하세요. 이 스킬은 그 정답표의 "근거 자체가 최신인가"를 담당합니다.
