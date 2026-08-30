<!--
project-session-memory 스킬의 정제된 누적 요약 파일입니다.
새 세션이 시작될 때 SessionStart 훅(.claude/hooks/session-memory-start.sh)이
이 파일 내용과 .claude/memory/inbox/(gitignore됨, 로컬 전용)의 미정리 캡처를
컨텍스트로 불러옵니다. inbox를 정리할 때 이 파일 아래에 날짜와 함께
핵심만 append하세요.
-->

## 2026-08-30

- PR 자동/수동 생성 판단은 "스킬"이 아니라 "규칙"(항상 적용되는 조건부
  행동)으로 분류하기로 함. 스킬은 특정 작업 유형에 매칭될 때만 발동하는
  절차이고, 규칙은 매 작업마다 적용되는 기본값이라 서로 다른 자리에 둔다.
- 저장소 루트에 `CLAUDE.md`를 새로 만들어 "주요 diff가 생기면 PR 생성 전
  사용자에게 먼저 확인한다" 규칙을 문서화함 (자동 생성이 아니라 확인 후
  생성 — PR 생성은 되돌리기 번거로운 행동이라 보수적인 쪽을 기본값으로
  선택). README에도 스킬 vs 규칙 구분과 `CLAUDE.md` 재사용 방법을 추가.
- 위치 결정: 전역 `~/.claude/CLAUDE.md`는 이 원격 세션 컨테이너가
  재생성되면 사라지므로 지속성이 없음 → my-skills 저장소의 `CLAUDE.md`에
  문서화하고, 다른 프로젝트엔 그 내용을 복사해 쓰는 방식을 채택.
- PR 생성 전 확인 규칙을 다른 프로젝트에 복사할 때는 그 프로젝트의 기존
  관례를 먼저 확인해야 함 — 프로젝트마다 규칙을 두는 자리가 다르다:
  - `korean-subtitle-corrector`: `CLAUDE.md`가 `@AGENTS.md`만 import하고
    실제 규칙은 `AGENTS.md`에 쓰는 관례라 거기에 새 섹션으로 추가.
  - `subtitle-tc-generator`: `CLAUDE.md` 자체가 번호 매긴 규칙 목록(0~17)을
    담고 있어서 "규칙 18"로 이어 붙임. 이 저장소는 `tools/hooks/pre-commit`이
    커밋 전 테스트를 강제하므로 `git config core.hooksPath tools/hooks` 설정
    후 테스트 통과를 확인하고 커밋해야 함.
  - 두 저장소 모두 PR을 만들 때 base 브랜치가 `master`(not `main`)였음 —
    기본 브랜치명을 가정하지 말고 `git remote show origin`으로 확인할 것.
