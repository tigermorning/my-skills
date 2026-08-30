---
name: durable-session-log
description: In remote/ephemeral environments where a fresh container spins up per session (Claude Code on the web, CI-driven agents, etc.), session context does not survive between sessions unless it is committed to git. Set up a git-tracked SESSION_LOG.md plus a SessionStart hook that automatically re-loads it at the start of each new session. Applies to any project run from such an environment, regardless of language or domain.
---

# Durable Session Log

컨테이너가 세션마다 새로 뜨는 원격 환경(Claude Code on the web 등)에서는 이전
세션의 맥락이 자동으로 남지 않습니다. 로컬 디스크는 세션이 끝나면 사라지므로,
**git 커밋으로 남긴 것만 다음 세션에 이어집니다.** 이 스킬은 그 맥락을 저장소
안에 로그 파일로 남기고, SessionStart hook으로 세션 시작 시 자동으로 불러오게
만듭니다.

기록은 Claude가 의미 있는 작업 단위가 끝날 때 **직접 적어야** 남는 수동
방식입니다 — 가볍지만, 적기를 깜빡하면 그 세션은 사라집니다. 기록을 자주
깜빡하거나 세션을 헷갈려서 새로 여는 일이 잦아 "최소한 뭔가는 자동으로
남았으면" 싶다면, 이 저장소의 `project-session-memory` 스킬(SessionEnd
훅으로 무조건 원본을 캡처하는 더 무거운 버전)을 대신 고려하세요. 한
프로젝트에 둘 다 설치할 필요는 없습니다.

## 왜 필요한가

- 원격 세션은 매번 저장소를 새로 clone한 컨테이너에서 시작한다. 이전 세션에서
  어떤 결정을 왜 내렸는지, 무엇을 미뤘는지는 커밋 메시지나 코드만으로는 잘
  드러나지 않는 경우가 많다.
- 노트북/PC 등 여러 기기를 오가며 작업할 때도 마찬가지다 — 세션 상태가 기기에
  묶여 있으면 기기를 바꾸는 순간 맥락이 끊긴다.
- git에 커밋된 파일은 두 문제를 동시에 해결한다: 컨테이너가 사라져도 남고,
  어느 기기에서 pull하든 동기화된다.

## 인식 신호 (다음 중 하나라도 해당하면 적용)

- 세션마다 컨테이너가 새로 뜨는 원격 실행 환경(Claude Code on the web, 기타
  클라우드 기반 에이전트 세션)에서 작업 중이다.
- 세션 간 이어지는 맥락(결정 사항, 미해결 질문, 다음에 할 일)이 존재하는데
  지금은 대화가 끝나면 사라진다.
- 여러 기기를 오가며 같은 프로젝트를 진행하고, 기기 간 맥락 동기화가
  필요하다.
- 반대로, 세션이 로컬 디스크에 영구히 남는 환경(개인 PC에서 상시 실행하는
  세션)이라면 이 패턴은 과잉이다 — 적용하지 않는다.

## 절차

1. **로그 파일 생성**: 프로젝트 루트에 `.claude/SESSION_LOG.md`를 만든다.
   파일 맨 위에 이 파일의 목적(세션 간 맥락 유지, SessionStart hook이 자동으로
   불러온다는 점, 의미 있는 작업 단위가 끝날 때마다 날짜/변경 내용/결정
   사항/미해결 질문을 추가하라는 지침)을 짧게 적는다.
2. **hook 등록**: `.claude/settings.json`에 `SessionStart` hook을 추가한다
   (기존 설정이 있으면 병합한다):

   ```json
   {
     "hooks": {
       "SessionStart": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "cat \"$CLAUDE_PROJECT_DIR/.claude/SESSION_LOG.md\" 2>/dev/null || true"
             }
           ]
         }
       ]
     }
   }
   ```

   `cat ... || true`로 파일이 아직 없거나 읽기 실패해도 세션 시작이 막히지
   않게 한다.
3. **검증**: hook 명령을 직접 실행해 로그 내용이 그대로 출력되는지 확인한다.
   ```bash
   CLAUDE_PROJECT_DIR="$(pwd)" bash -c 'cat "$CLAUDE_PROJECT_DIR/.claude/SESSION_LOG.md" 2>/dev/null || true'
   ```
4. **커밋·push**: 두 파일을 커밋하고 origin에 push한다. main/master에 바로
   push하지 않는 저장소 관례가 있다면 그것을 따른다.
5. **이후 사용**: 의미 있는 작업 단위(기능 하나 완료, 중요한 결정, 다음
   세션에 넘길 미해결 질문 등)가 끝날 때마다 `SESSION_LOG.md`에 날짜별
   항목을 추가하고 커밋한다. 로그가 무한정 길어지면 오래된 항목은 요약하거나
   별도 아카이브 파일로 옮긴다 — 매 세션 시작마다 전체가 hook으로 출력되므로
   너무 길면 컨텍스트를 낭비한다.

## 하지 않는 것

- 세션 상태를 로컬 파일이나 컨테이너 안에만 남기고 커밋하지 않기 — 다음
  세션에서 사라진다.
- 로그를 무한정 append만 하고 정리하지 않기 — hook이 매번 전체를 출력하므로
  길어질수록 세션 시작 비용이 커진다.
- 민감 정보(토큰, 자격증명, 개인정보)를 로그에 적지 않기 — git 이력에 영구히
  남는다.

## 실제 적용 사례

`korean-subtitle-corrector` 저장소에 이 패턴을 그대로 적용해
`.claude/SESSION_LOG.md` + `.claude/settings.json`의 `SessionStart` hook으로
설치한 사례가 있다 (2026-08-30). 새 프로젝트에 적용할 때 참고할 수 있다.
