---
name: project-session-memory
description: Sets up automatic cross-session memory for a specific project/repo, so a new Claude Code session (or a session the user got confused and reopened) already knows what happened in previous sessions on that same project, without the user re-explaining context. Use whenever the user wants Claude to "remember" past conversations for a project, complains about repeating themselves across sessions, or asks to persist project context/decisions/progress between sessions. This installs a SessionEnd hook (captures a raw excerpt of each session) and a SessionStart hook (loads that project's memory back into context) into the target project's .claude/ directory — it is infrastructure, not just conversational advice, so it only fully works once actually installed into that project.
---

# Project Session Memory

한 프로젝트 안에서 세션이 여러 번 나뉘어도(사용자가 세션을 헷갈려서 새로
열었을 때 포함) Claude가 이전 세션에서 무슨 일이 있었는지 다시 설명 없이
알 수 있게, 훅으로 자동 저장·자동 로드를 구현합니다.

## durable-session-log와 뭐가 다른가

이 저장소에는 비슷한 목적의 `durable-session-log` 스킬도 있습니다. 그건
Claude가 의미 있는 작업 단위가 끝날 때마다 `SESSION_LOG.md`에 직접
기록해야 남는 **수동** 방식이라 가볍고 단순합니다 — 대신 기록을 깜빡하면
그 세션은 통째로 사라집니다.

이 스킬은 그 반대 극단입니다: `SessionEnd` 훅이 세션이 끝나기만 하면
Claude의 판단 없이 원본 일부를 무조건 캡처합니다. 대신 그만큼 구조가
복잡하고(정제 안 된 원본이 `.claude/memory/inbox/`에 쌓이고, 정리는
다음 세션의 Claude에게 맡겨짐), 커밋 여부를 판단해야 할 원본 텍스트가
생깁니다.

**기록하는 습관이 있고 가볍게 가고 싶다면 `durable-session-log`를 먼저
고려하세요.** 그걸 자주 깜빡하거나, 세션을 헷갈려서 새로 여는 일이 잦아서
"최소한 뭔가는 자동으로 남았으면 좋겠다"는 요구가 있을 때 이 스킬을
씁니다. 한 프로젝트에 둘 다 설치하면 SessionStart 훅이 두 번 실행되어
같은 맥락이 중복으로 컨텍스트에 실릴 수 있으니, 보통은 하나만 고릅니다.

## 왜 Stop 훅이 아니라 SessionEnd + SessionStart인가

가장 먼저 떠오르는 방법은 "세션이 끝날 때 Stop 훅으로 요약을 시키자"지만,
`Stop` 훅은 세션이 끝날 때가 아니라 **매 턴(응답 한 번)이 끝날 때마다**
발동합니다. 이걸로 요약을 강제하면 대화 내내 매번 "먼저 메모리 파일에
기록하고 나서 멈춰"라고 끼어들게 되어 사용자 경험을 해칩니다.

반대로 `SessionEnd` 훅은 세션이 실제로 끝날 때(창 닫기, `/clear`, 로그아웃
등) 딱 한 번만 불리지만, 셸 스크립트만 실행할 뿐 모델에게 아무것도
돌려줄 수 없고(추가 컨텍스트 주입 불가), 공유 타임아웃 예산도 기본
1.5초로 매우 빠듯합니다. 즉 **SessionEnd는 Claude에게 "요약해줘"라고
시킬 수 없는 자리**입니다.

그래서 역할을 나눕니다:

- **SessionEnd** (기계적, 빠름): 방금 끝난 세션의 transcript 꼬리 부분을
  그대로 `.claude/memory/inbox/<session_id>.md`에 저장만 합니다. 요약
  안 함, 판단 안 함 — 그냥 원본 캡처.
- **SessionStart** (판단은 다음 세션의 Claude가): 새 세션이 시작되면
  `.claude/memory/session-log.md`(정제된 누적 요약)와 아직 정리 안 된
  `.claude/memory/inbox/*.md`(원본 캡처)를 컨텍스트로 주입합니다. 그리고
  inbox가 쌓여 있으면 "적당한 시점에 훑어보고 중요한 것만
  session-log.md에 정리한 뒤 inbox는 지워라"라고 다음 세션의 Claude에게
  안내합니다. 이 정리는 강제(block)가 아니라 컨텍스트로만 전달되므로,
  실제 요약 시점과 품질은 그 세션의 Claude 판단에 맡깁니다 — 하지만 그
  전까지도 inbox 원본이 이미 컨텍스트에 들어가 있으므로 "이전 세션 내용을
  전혀 모른다"는 상황은 생기지 않습니다.

## 설치 절차 (대상 프로젝트에 적용)

사용자가 "이 프로젝트에도 세션 메모리 켜줘" 같은 요청을 하면, **이
스킬이 있는 저장소가 아니라 사용자가 지금 작업 중인 프로젝트**에 다음을
설치하세요:

1. 이 스킬 디렉터리의 `scripts/session-memory-end.sh`와
   `scripts/session-memory-start.sh`를 대상 프로젝트의
   `.claude/hooks/`로 복사하고 실행 권한을 유지합니다
   (`chmod +x`).
2. 대상 프로젝트의 `.claude/settings.json`에 아래 훅 등록을 병합합니다
   (파일이 없으면 새로 만들고, 있으면 기존 `hooks` 키 아래에 합칩니다 —
   덮어쓰지 마세요):

   ```json
   {
     "hooks": {
       "SessionStart": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session-memory-start.sh"
             }
           ]
         }
       ],
       "SessionEnd": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session-memory-end.sh",
               "timeout": 10
             }
           ]
         }
       ]
     }
   }
   ```

   `SessionEnd`의 기본 타임아웃 예산(1.5초)은 transcript가 크면 빠듯할 수
   있어 `timeout`을 넉넉히 잡습니다. `SessionStart`/`SessionEnd` 둘 다
   `matcher`는 생략해도 모든 경우(startup/resume/clear 등)에 걸립니다.

3. `.claude/memory/`와 `.claude/memory/inbox/`를 만들고, 팀과 공유할
   프로젝트라면 `.gitignore`에 `.claude/memory/inbox/`를 추가할지
   사용자에게 물어보세요 (원본 대화 캡처는 노이즈가 많고 민감한 내용이
   섞일 수 있어 커밋하지 않는 편이 보통 낫습니다). `session-log.md`는
   정제된 요약이라 커밋해서 팀원과 공유해도 되는지도 사용자 선호에
   맡기세요.
4. `jq`가 설치돼 있는지 확인하세요 (`command -v jq`) — 두 스크립트 모두
   transcript의 JSONL을 파싱하는 데 사용합니다. 없으면 설치를 안내하거나,
   그 환경에서 무리라면 이 스킬 적용이 어렵다고 사용자에게 알리세요.
5. 설치 후 두 스크립트를 실제로 실행해 검증하세요 (예: 가짜 stdin JSON을
   파이프로 넣어 `session-memory-end.sh`가 `inbox/`에 파일을 만드는지,
   `session-memory-start.sh`가 유효한 JSON을 stdout에 내는지 `jq .`로
   확인). 다음 세션부터 실제로 작동합니다 — 지금 세션에는 적용되지
   않습니다.

## 이 스킬이 하지 않는 것

- **매 턴 요약을 강제하지 않습니다** — Stop 훅을 쓰지 않는 이유는 위
  설명대로입니다.
- **inbox를 자동으로 요약해서 지우지 않습니다** — 그건 셸 스크립트가
  판단할 수 없는 일이라 다음 세션의 Claude에게 컨텍스트로만 넘깁니다.
  즉 inbox가 무한정 쌓이는 것을 막으려면, 세션 시작 시 이 안내를 실제로
  실행에 옮겨야 합니다 (컨텍스트에 안내가 있다고 자동으로 되는 게
  아니라, 이어지는 대화에서 "적당한 시점에" 실행돼야 하는 일임을
  기억하세요).
- **다른 프로젝트와 메모리를 공유하지 않습니다** — 저장 위치가 각
  프로젝트의 `.claude/memory/`이므로 프로젝트별로 완전히 분리됩니다.
- **비밀번호·토큰 같은 민감정보를 걸러주지 않습니다** — transcript를
  그대로 캡처하므로, 세션 중 민감정보가 오갔다면 inbox 파일에도 그대로
  남습니다. 커밋 전에는 항상 내용을 확인하세요.
