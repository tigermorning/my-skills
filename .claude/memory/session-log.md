<!--
project-session-memory 스킬의 정제된 누적 요약 파일입니다.
새 세션이 시작될 때 SessionStart 훅(.claude/hooks/session-memory-start.sh)이
이 파일 내용과 .claude/memory/inbox/의 미정리 캡처를 컨텍스트로 불러옵니다.
inbox를 정리할 때 이 파일 아래에 날짜와 함께 핵심만 append하세요.
-->

## 2026-08-30

- `project-session-memory`/`durable-session-log` 스킬이 목적이 겹쳐서, 삭제하지
  않고 SKILL.md·README 양쪽에 "언제 뭘 쓸지" 구분을 추가하는 쪽으로 정리함
  (durable-session-log = 수동/가벼움, project-session-memory = 자동 캡처/무거움).
- `.claude/memory/inbox/`는 원래 프라이버시 때문에 gitignore했었는데, 원격
  환경에서는 gitignore된 파일이 다음 세션으로 절대 안 넘어간다는 걸 실제
  검증(새 원격 세션 spawn + 클린 clone 테스트)으로 확인함. 그래서 SessionEnd가
  inbox 캡처를 로컬 `git commit`까지는 하도록 바꿈.
- 다만 `git push`까지 자동으로 하는 건 Claude Code auto-mode 분류기가 차단함
  (세션 종료마다 무인으로 push하는 훅은 리스크가 다르다고 판단한 것으로 보임).
  그래서 커밋까지만 자동화하고, 실제 push는 이후 정상적인 작업 흐름에서 이뤄지는
  걸 전제로 함 — 즉 컨테이너가 완전히 회수되기 전에 아무 push도 없으면 그 세션의
  캡처는 여전히 유실될 수 있음 (이건 알려진 한계로 남겨둠, 일반적인 미푸시 커밋과
  같은 수준의 리스크).
