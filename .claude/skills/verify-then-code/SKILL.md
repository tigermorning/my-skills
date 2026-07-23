---
name: verify-then-code
description: Before implementing a new rule or classification that may have exceptions (grammar rules, business rules, formatting rules, tax/legal conditions, anything with an authoritative-but-irregular source of truth), build a verified "input → correct answer" table from authoritative sources first, then write code that matches the table. Applies whenever the domain has an authority to check against and exceptions are plausible.
---

# Verify Then Code

새 규칙을 다룰 때 "이럴 것이다"라는 가정으로 코드부터 짜지 마세요. 권위 있는 근거로
정답표를 먼저 만들고, 코드는 그 표를 따라가게 하세요.

## 왜 필요한가

예외가 있을 수 있는 규칙(문법 활용형, 세금·법률 조건, 데이터 분류 기준 등)을
"규칙이 대충 이럴 것"이라는 추측으로 먼저 구현하면, 나중에 실제 예외 사례가
나왔을 때 코드를 땜질식으로 계속 패치하게 됩니다. `korean-subtitle-corrector`
프로젝트에서 이 방식으로 같은 실수(보조 용언 "할만하다"류 오교정)를 두 번
반복하고 나서야 확립된 절차입니다.

## 언제 적용

- 다루는 대상에 예외·애매한 경우가 존재할 수 있는 규칙일 때 (예외 없는 단순
  고정 치환에는 이 절차가 필요 없음)
- 권위 있는 근거(공식 문서, 표준, 사전/규범 API, 법령 등)를 조회할 수 있는
  도메인일 때

## 절차

1. **경우의 수 나열**: 해당 규칙에 들어갈 수 있는 표현/케이스를 가능한 만큼
   전부 나열한다 (변형, 준말, 흔한 엣지 케이스 포함).
2. **정답표 작성**: 각 케이스를 권위 있는 근거로 직접 조회해 "입력 → 정답"
   표를 만든다. 코드를 짜기 **전에** 표부터 완성한다. 근거로도 애매하거나
   문맥 의존적이면 그 케이스는 "자동 처리 대상 아님, 항상 사람 확인"으로
   명시한다 — 억지로 단일 정답을 만들지 않는다.
3. **표에 맞춰 코드 작성**: 정답표에 정확히 일치하는 로직만 짠다. 코드가
   표를 따라가는 것이지, 표가 코드를 사후 검증하는 게 아니다.
4. **새 사례 발견 시**: 구현 후 표에 없던 사례가 나오면 코드를 임시로
   패치하지 않는다. 먼저 그 사례를 정답표에 추가(2번 절차로 재조회)한 뒤,
   갱신된 표에 맞춰 코드를 고친다.
5. **회귀 테스트**: 새 사례를 테스트에 고정해 이후 실수로 되돌아가지 않게
   한다.

## 하지 않는 것

- "아마 이럴 것"이라는 가정으로 코드부터 작성하지 않기
- 예외 발견 시 표 갱신 없이 코드만 패치하지 않기
- 애매한 케이스를 억지로 단일 정답으로 확정하지 않기

## 관련 스킬

실사용 데이터로 결과를 검증하는 단계는 [[real-world-review-cycle]]을 참고하세요.
