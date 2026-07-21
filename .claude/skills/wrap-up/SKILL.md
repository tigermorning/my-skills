---
name: wrap-up
description: Review pending changes, draft a commit message in the project's own style, and commit — for when a change is done and you just want to say "커밋해줘" / "wrap this up" instead of walking the AI through status → diff → message → commit every single time.
---

# Wrap Up

방금 끝낸 작업을 커밋 가능한 상태로 정리합니다. "커밋해줘", "정리해줘", "wrap up", "commit this" 같은 요청에 반응하세요.

## 왜 이 스킬이 필요한가

작업이 끝날 때마다 사람이 매번 이 세 가지를 다시 해야 했습니다:
1. 뭐가 바뀌었는지 다시 설명하고
2. 이 프로젝트의 커밋 메시지 스타일을 다시 알려주고
3. "이제 커밋해"라고 명시적으로 말해야 했습니다.

이 스킬은 그 세 단계를 한 번에 묶습니다.

## 절차

1. `git status --short --branch`와 `git diff`(스테이지 안 된 변경) / `git diff --staged`(이미 스테이지된 변경)로
   실제 바뀐 내용을 직접 확인하세요. 추측하지 말고 반드시 확인하세요.
2. `git log --oneline -10`으로 이 저장소의 기존 커밋 메시지 스타일(언어, 어투, 포맷)을 파악하고 맞추세요.
3. 관련 없는 파일(로그, 임시 파일, `.env`, 빌드 산출물, 시크릿으로 보이는 파일)은 제외하고
   실제로 의도한 변경에 해당하는 파일만 `git add`로 스테이징하세요.
4. 커밋 메시지는 "무엇을 바꿨는지"보다 "왜 바꿨는지"를 중심으로, 1~2문장으로 짧게 쓰세요.
5. 커밋한 뒤 `git log --oneline -3`으로 결과를 확인하고, 무엇을 커밋했는지 한 줄로 보고하세요.
6. **커밋까지만 하고 push는 하지 마세요** — push는 항상 별도의 명시적 요청이 있을 때만 하세요.

## 하지 않는 것

- `git add -A`로 무차별 스테이징하지 않기 — 뭐가 올라가는지 항상 먼저 확인
- 시크릿/자격증명처럼 보이는 파일이 스테이징 대상에 있으면 커밋 전에 먼저 사용자에게 알리기
- 실제 diff에 없는 내용을 커밋 메시지에 지어내지 않기
- 이미 커밋을 지시받지 않았는데 먼저 나서서 커밋하지 않기 (요청이 있을 때만 발동)
