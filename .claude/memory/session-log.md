<!--
project-session-memory 스킬의 정제된 누적 요약 파일입니다.
새 세션이 시작될 때 SessionStart 훅(.claude/hooks/session-memory-start.sh)이
이 파일 내용과 .claude/memory/inbox/(gitignore됨, 로컬 전용)의 미정리 캡처를
컨텍스트로 불러옵니다. inbox를 정리할 때 이 파일 아래에 날짜와 함께
핵심만 append하세요.
-->

### 2026-08-30: PR #7 merge, 언어 혼용 조사

- `durable-session-log`를 `project-session-memory`로 통합하는 PR #7을 merge함.
  이제 이 레포의 세션 기억 스킬은 `project-session-memory` 하나뿐.
- 사용자가 "깃허브에 한국어/영어가 혼재된 것 같다"고 지적 → `my-skills`와
  `subtitle-tc-generator`(별도 세션에 위임해서 조사) 둘 다 스캔한 결과 실수로
  섞인 곳은 없었음. 두 레포 모두 "메타데이터(커밋/PR/frontmatter)=영어,
  설명·문서=한국어"라는 동일한 의도된 분리 패턴을 따르고 있었음 — 사용자가
  느낀 "혼재"는 이 패턴이 여러 레포에 걸쳐 보이면서 생긴 인상으로 추정됨.
  korean-subtitle-corrector, who-ate-my-cheesecake, blog는 아직 미확인
  (사용자가 원하면 이어서 조사).
