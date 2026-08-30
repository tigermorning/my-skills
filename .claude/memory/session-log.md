<!--
project-session-memory 스킬의 정제된 누적 요약 파일입니다.
새 세션이 시작될 때 SessionStart 훅(.claude/hooks/session-memory-start.sh)이
이 파일 내용과 .claude/memory/inbox/의 미정리 캡처를 컨텍스트로 불러옵니다.
inbox를 정리할 때 이 파일 아래에 날짜와 함께 핵심만 append하세요.
-->

## 2026-08-30

- `project-session-memory`/`durable-session-log` 스킬 중복 문제: 여러 동시
  세션에 걸쳐 (1) 둘 다 유지+구분 설명 → (2) 통합(PR #7 머지) → (3) 통합
  revert → (4) **사용자가 직접 "하나로 정리해달라"고 요청**해서
  `durable-session-log`를 최종 삭제하고 `project-session-memory` 하나로
  확정. `project-kickoff` SKILL.md의 참조도 `durable-session-log` →
  `project-session-memory`로 갱신함. **이게 최종 결정입니다 — 다시 되돌리지
  마세요.** (같은 저장소를 여러 세션이 동시에 건드리면서 이 결정이 세 번
  뒤집힌 사례이니, 만약 또 뒤집혀 있는 걸 발견하면 사용자에게 왜 그런지
  물어보고 넘어갈 것.)
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
- `project-session-memory`를 실제로 다른 프로젝트 3곳에 설치함:
  `subtitle-tc-generator`(master 직접 push), `who-ate-my-cheesecake`(PR #7
  머지), `korean-subtitle-corrector`(PR #6 머지, 기존 revert된
  durable-session-log 자리를 대체). 세 곳 다 설치 전 가짜 stdin으로 훅을
  직접 실행해 검증 후 커밋함. 사용자가 "다른 프로젝트도 필요하면 나중에
  더 설치해달라"고 함 — 앞으로 활성 프로젝트가 생기면 이 패턴(레포 관례
  확인 → 설치 → 훅 테스트 → 커밋/PR)을 그대로 반복하면 됨.
