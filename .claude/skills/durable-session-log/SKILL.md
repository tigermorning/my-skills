---
name: durable-session-log
description: For any project revisited across many separate Claude Code sessions — especially ephemeral remote/web sessions where the container and its home directory are thrown away between sessions — keep a git-committed session log file and wire a SessionStart hook to auto-inject it at the start of every session. This makes cross-session continuity survive container resets, unlike anything stored outside the repo (e.g. under ~/.claude), which vanishes when the container is recycled. Pairs with decision-log: this is the mechanism that keeps decision-log's record alive and loaded without relying on remembering to check it.
---

# Durable Session Log

세션마다 컨테이너가 새로 뜨는 원격 환경에서는, 저장소에 커밋되지 않은
정보는 전부 사라집니다. 세션 간 기억을 유지하려면 로그 파일을 **저장소에
커밋**하고, 세션 시작 시 자동으로 그걸 불러오는 hook을 걸어야 합니다.

## 왜 필요한가

`decision-log` 스킬은 "답하기 전에 기록을 확인하라"고 하지만, 그 확인이
"모델이 기억해서 파일을 여는 것"에 의존하면 똑같이 깜빡할 수 있습니다.
게다가 Claude Code on the web 같은 원격 세션은 비활성 상태가 되면
컨테이너가 회수되고, 다음 세션은 완전히 새 컨테이너에서 저장소를 다시
클론해서 시작합니다. `~/.claude`나 홈 디렉터리에만 저장되는 정보(예:
서드파티 메모리 플러그인의 로컬 DB)는 이 리셋에서 살아남지 못합니다 —
저장소에 커밋된 파일만 확실하게 다음 세션에도 남습니다.

## 인식 신호 (다음 중 하나라도 해당하면 적용)

- 이 프로젝트를 여러 번의 개별 Claude Code 세션에 걸쳐 계속 다시 찾아온다
  (특히 원격/웹 세션처럼 세션마다 컨테이너가 새로 뜨는 환경).
- "지난 세션에 뭘 했는지" 또는 "이 프로젝트에서 이미 확인/결정한 것"을
  매번 대화로 다시 설명해야 하는 게 반복되고 있다.
- 메모리 유지를 홈 디렉터리 상태(플러그인 로컬 DB, 전역 설정)에만 의존하고
  있는데, 그 환경이 세션마다 초기화되는지 확인 안 된 상태다.
- 반대로, 한 번 열고 끝나는 일회성 작업이거나 항상 로컬 고정 머신에서만
  작업한다면(홈 디렉터리가 세션 간 유지됨) 이 절차는 불필요할 수 있다.

## 절차

1. **로그 파일 위치 확정**: 저장소 안에 `.claude/SESSION_LOG.md` 같은
   커밋 대상 파일을 만든다 (`.gitignore`에 걸려있지 않은지 확인).
2. **SessionStart hook 등록**: `.claude/settings.json`에 세션 시작 시
   이 파일 내용을 자동으로 컨텍스트에 주입하는 hook을 건다.
   ```json
   {
     "hooks": {
       "SessionStart": [
         { "hooks": [ { "type": "command",
           "command": "cat \"$CLAUDE_PROJECT_DIR/.claude/SESSION_LOG.md\" 2>/dev/null || true" } ] }
       ]
     }
   }
   ```
   이렇게 하면 모델이 "기억해서 파일을 열어야겠다"고 판단할 필요 없이,
   harness가 매 세션 시작마다 강제로 주입한다.
3. **세션 종료 시 기록**: 의미 있는 작업 단위가 끝날 때마다(또는 세션을
   마무리할 때) `decision-log` 형식대로 날짜, 결론, 근거를 이 파일에
   추가한다.
4. **커밋**: 로그 파일 변경을 **반드시 커밋하고 푸시**한다. 로컬/컨테이너
   안에만 남겨두면 다음 세션이 새 컨테이너에서 시작할 때 사라진다.
5. **길이 관리**: 파일이 너무 길어지면(수십 개 세션 누적) 오래된 항목을
   요약해서 압축하거나 월별 파일로 분리한다 — 매 세션 시작마다 전체를
   주입하는 비용을 억제한다.

## 하지 않는 것

- 로그를 홈 디렉터리나 세션 로컬 상태에만 남기고 커밋하지 않기 (원격
  환경에서는 다음 세션에 사라짐)
- SessionStart hook 없이 "다음에 파일을 열어봐야지"라고 모델의 기억에만
  의존하기
- 로그를 무한정 누적만 하고 요약/정리 없이 방치하기

## 관련 스킬

기록을 확인하고 검증하는 행동 원칙은 [[decision-log]]를 참고하세요. 이
스킬은 그 기록이 세션 간에 실제로 살아남고 자동으로 불러와지게 만드는
인프라입니다.
