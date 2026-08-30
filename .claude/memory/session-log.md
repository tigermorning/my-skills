<!--
project-session-memory 스킬의 정제된 누적 요약 파일입니다.
새 세션이 시작될 때 SessionStart 훅(.claude/hooks/session-memory-start.sh)이
이 파일 내용과 .claude/memory/inbox/의 미정리 캡처를 컨텍스트로 불러옵니다.
inbox를 정리할 때 이 파일 아래에 날짜와 함께 핵심만 append하세요.
-->

## 2026-08-30

- `project-session-memory`/`durable-session-log` 스킬 중복 문제로 이 저장소
  안에서 왔다 갔다가 있었음: (1) 처음엔 둘 다 유지 + 구분 설명 추가,
  (2) 다른 동시 세션이 `durable-session-log`를 삭제하고 하나로 통합(PR #7
  머지), (3) 또 다른 동시 세션이 그 통합을 다시 revert해서 durable-session-log가
  복원됨. **지금(이 노트 시점) 카탈로그엔 둘 다 다시 존재함.** 같은 저장소를
  여러 세션이 동시에 건드리면서 같은 결정이 반복적으로 뒤집힌 사례 — 다음
  세션은 이 항목이 또 바뀌어 있을 수 있으니 README/SKILL.md를 실제로 확인할 것.
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
