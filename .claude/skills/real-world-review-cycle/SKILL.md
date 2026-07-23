---
name: real-world-review-cycle
description: Don't judge correctness by reading code alone — run it against real-world input (real text, real data, real requests) and reconcile the output by hand. Split mismatches into "confirmed bug → fix the root cause now" vs "needs human judgment → leave flagged, don't force an automated answer." Applies to parsers, correctors, classifiers, generators, or anything whose correctness can't be fully judged by reading the code.
---

# Real World Review Cycle

코드만 읽고 "됐다"고 판단하지 마세요. 실제 입력(실사용 텍스트, 실 데이터,
실 요청 등)으로 돌려서 결과를 사람이 직접 대조 검토하세요.

## 왜 필요한가

파서·교정기·분류기·생성기처럼 입력 공간이 넓은 로직은, 코드를 아무리
꼼꼼히 읽어도 실제 입력에서만 드러나는 버그를 놓치기 쉽습니다.
`korean-subtitle-corrector` 프로젝트에서 이 절차를 반복 적용해 코드 리뷰만으로는
발견하지 못했던 실제 버그(오조회로 인한 오교정, 음절 중복 출력 등)를 여러 번
잡아냈습니다.

## 언제 적용

- 새 기능을 구현한 뒤 검증할 때
- 입력 공간이 넓어 코드 리딩만으로 정확성을 보장하기 어려운 로직
  (파서, 교정기, 분류기, 생성기, 규칙 엔진 등)
- 정기적으로 실사용 감수를 하고 싶을 때

## 절차

1. **실제 입력 준비**: 실사용 텍스트/데이터를 스크래치패드 등 임시 위치에
   둔다. 저작권·개인정보가 있는 원본은 **리포에 커밋하지 않는다.**
2. **실행**: 대상 기능을 실제 입력에 돌려 결과(자동 처리 결과 + 플래그
   리포트 등)를 얻는다.
3. **대조 검토**: 원본의 의도와 결과를 사람이 직접 대조한다. 각 불일치를
   두 갈래로 분류한다:
   - **확실한 버그** (근거와 명백히 다르게 동작함, 알려진 한계에 해당하지
     않는 새로운 오탐/미탐) → 원인을 코드에서 추적해 **즉시 근본 원인을
     수정**한다. 임시 패치 금지. 예외 있는 규칙이면 [[verify-then-code]]
     절차를 따른다.
   - **판단이 필요한 애매한 사례** (문맥에 따라 답이 갈림, 근거 자체가
     없음, 원칙상 항상 사람 확인이 필요한 영역) → 코드를 건드리지 않는다.
     올바르게 플래그되고 있는지만 확인한다.
4. **회귀 확인**: 수정 후 기존 테스트/샘플로 기존 동작이 깨지지 않았는지
   재확인한다.
5. **기록**: "N차 실사용 감수: 오탐/미탐 M건 조사, 확실한 버그 K건 수정"
   형식으로 발견 경위와 수정 내용을 구체적으로 남긴다. 판단 필요 사례로
   남긴 것도 왜 자동화하지 않았는지 간단히 남긴다.

## 하지 않는 것

- 코드 리딩만으로 검증 완료라고 판단하지 않기
- 애매한 사례를 억지로 자동 처리하지 않기
- 판단 근거 없이 코드를 임시 패치하지 않기

## 관련 스킬

예외가 있는 규칙을 코드화할 때는 [[verify-then-code]]를 먼저 참고하세요.
