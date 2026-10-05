---
name: pr-pipeline
description: Run a finished feature branch through the whole PR pipeline so a person only reads the PRs that need one - repo checks, a headless review agent (claude -p, no shell, writes only fix files and the body) whose sure fixes the pipeline commits, with questions and the PR body, the pr-merge-danger body check against the real diff and the user's one-way rules, push and PR, CI, then a merge verdict. Auto-merges only when the repo opted in and every condition holds (checks and CI green, two-way door, no one-way signal, no review question, small, no protected path); otherwise the PR stays open with the reasons as a comment. Use when an agent finishes work on a branch, when the user says to open or ship a PR, when agent PRs pile up, or when setting up "humans only review one-way doors" for a repo. Needs <repo>/.claude/pr-pipeline.json.
---

# PR Pipeline — 사람은 판정이 보낸 PR 만 본다

[[standards-review]] · [[pr-merge-danger]] · [[review-retro]]가 각각 손으로 부르는 부품이라면,
이 스킬은 그것들을 **한 번에, 매번 같은 순서로** 돌리는 흐름이다.
사람 리뷰가 실제로 줄어드는 곳은 마지막 판정이다: 되돌릴 수 있고 작고 초록인 변경은 사람 없이 지나가고,
나머지만 이유와 함께 사람에게 간다.

출처: Matt Pocock, "Fixing the PR Bottleneck"(AI Engineer Paris 2026) — 자동 검사 → 자동 리뷰 → 사람 리뷰,
"two-way door 는 전부 볼 필요 없다, one-way door 는 전부 본다".

## 인식 신호

- 에이전트(또는 내가)가 기능 브랜치의 일을 끝냈다.
- 사용자가 "PR 올려 줘", "보내 줘", "머지할 수 있게 해 줘"라고 했다.
- 에이전트 PR 이 쌓이고 사람이 다 못 본다.
- 저장소에 "사람은 one-way 만 본다"를 처음 세운다.

해당 없음: 저장소에 `.claude/pr-pipeline.json` 이 없으면 먼저 만든다(아래 준비). 기준 브랜치에서 직접 일한 변경.

## 흐름

```
preflight ─▶ checks ─▶ review(claude -p) ─▶ checks again ─▶ door(판정 3명) ─▶ body check ─▶ push·PR·CI ─▶ verdict
  깨끗한가     실패면 멈춤   수정안·질문·본문→커밋   깨지면 리뷰 커밋 revert   하나라도 예면 one-way   pr-merge-danger      (--dry-run 은 생략)   자동 머지 / 사람에게
```

| 단계 | 하는 일 | 멈추는 때 |
|---|---|---|
| preflight | 기준 브랜치가 아닌지, 작업 트리가 깨끗한지, 앞선 커밋이 있는지 | 하나라도 아니면 종료 코드 2 |
| checks | 설정의 `checks` 명령을 차례로(환경변수는 `check_env`) | 실패면 종료 코드 1, 리뷰는 안 돎 |
| review | 사람 없이 리뷰 에이전트. 셸이 없고 저장소를 못 고친다 — 파이프라인이 준 diff·커밋 목록·검사 출력을 읽고, 임시 폴더에 수정안 파일(아래)·PR 본문을 쓰고, 나머지는 질문. 파이프라인이 수정안을 하나씩 적용해 `review:` 커밋 | 리뷰 중 트리가 바뀌면 종료 코드 1 |
| checks again | 리뷰 커밋 뒤 다시 | 깨지면 리뷰 커밋을 `git revert` 하고 질문으로 남김 |
| door | 리뷰와 따로 `claude -p` 판정 `door_runs`명(기본 3, 동시에). 고정 체크리스트(아래) 항목마다 예/아니오와 근거. 한 명이라도 한 항목에 예, 또는 쓸 만한 답이 없으면 one-way. 파이프라인이 본문의 Merge Danger 절을 이 결과로 쓴다(리뷰어는 안 씀) | — |
| body | `check_pr_body.py`: 세 절, Door, 실제 diff 의 one-way 신호, 사용자 공통 위험 목록 | 본문이 없으면 종료 코드 1 |
| publish | push, PR 만들기 또는 본문 갱신, CI 기다림 | — |
| verdict | 아래 조건 | — |

### Door 체크리스트 (판정이 항목마다 답한다)

| 항목 | 예가 되는 때 (머지된 코드가 실행될 때) |
|---|---|
| data_loss | 사람이 가진 데이터·파일을 지우거나 덮어씀(자기 임시·빌드 파일 제외) |
| migration | 저장 형식·스키마를 옛 버전이 못 읽게 바꿈 |
| outbound | 다른 사람·서비스에 무언가 보냄: 메시지, 메일, PR·이슈 댓글, 웹훅 |
| publishing | push, 배포, 릴리스, 업로드처럼 남이 볼 수 있게 내보냄 |
| secrets | 자격 증명·토큰·키를 더하거나 옮기거나 드러냄 |
| public_contract | 남이 이미 쓰는 CLI 옵션·파일 형식·API·설정 키를 없애거나 이름·뜻을 바꿈(새 선택 항목 추가는 아님) |
| external_state | revert 로 안 되돌아가는 저장소 밖 상태를 바꿈(설정, 계정, 원격 브랜치, 돈) |

- 이 PR 을 머지하는 행위 자체는 판단하지 않는다. 공개 저장소에 머지한다고 게시가 되지는 않는다.
- 이 변경 전부터 하던 일이면 아니오. diff 가 그 동작을 새로 넣거나 바꿀 때만 예.
- 글자 검사(`publish or push` 등) 결과를 힌트로 준다. 판정이 코드로 확인한다.

### 수정안 파일 (리뷰어 → 파이프라인)

```json
{"subject": "review: <무엇>", "edits": [{"path": "<저장소 루트 기준 경로>", "old": "<파일에 정확히 한 번 나오는 글>", "new": "<바꿀 글>"}]}
```

- 리뷰어가 임시 폴더 `fixes/01.json`, `02.json` … 으로 쓴다. 파이프라인이 이름 순서로 하나씩 적용해 각각 커밋 하나.
- 버리고 질문으로: 바뀐 파일 밖·저장소 밖 경로, `old` 가 0번이나 여러 번 나옴, 바뀌는 게 없음, 커밋 훅 실패. 한 수정안의 편집은 전부 되거나 전부 안 된다.
- 손으로 쓴 unified diff 대신 이 형식: 줄 번호를 세지 않아도 되고, 줄 끝이 CRLF 인 파일도 맞춰 준다.

**자동 머지 조건 (전부)**

- 로컬 검사와 CI 초록(CI 가 없는 저장소는 로컬 검사만)
- 본문 검사 통과, Door 가 two-way
- one-way 신호 없음(기본 목록 + 사용자 공통 목록), 사용자 `block` 규칙에 안 걸림
- 리뷰 질문 0 (리뷰 커밋이 바뀐 파일 밖을 건드렸으면 질문이 된다)
- 변경 줄 수 ≤ `max_changed_lines`, `protected_paths` 를 안 건드림

하나라도 어긋나면 PR 은 열린 채 남고, 어긋난 조건 전부가 PR 댓글("pr-pipeline 판정")과 출력에 적힌다.
`auto_merge` 가 꺼져 있으면 조건을 다 맞아도 머지하지 않고 "조건 충족"만 적는다 — 사람이 한 마디로 머지한다.

## 준비 (저장소당 한 번)

1. `scripts/config.example.json` 을 `<repo>/.claude/pr-pipeline.json` 으로 복사해 고친다.
   - `base`: 기준 브랜치 · `checks`: 몇 분 안에 끝나는 검사 명령 · `check_env`: 검사용 환경변수
   - `auto_merge`: **처음엔 `false`** — 판정만 몇 번 보고 믿게 되면 켠다
   - `protected_paths`: 사람이 꼭 볼 경로(훅·CI 설정·마이그레이션 등) · `after_merge`: 머지 뒤 명령(`{branch}`)
2. 사용자 공통 규칙 파일이 있으면 리뷰어와 본문 검사가 같이 읽는다([[standards-review]] "두 층").
3. `claude`(Claude Code CLI)와 `gh`(로그인)가 있어야 한다.

## 쓰는 법

```bash
python ~/.claude/skills/pr-pipeline/scripts/pr_pipeline.py run --dry-run
```

```bash
python ~/.claude/skills/pr-pipeline/scripts/pr_pipeline.py run
```

- 먼저 `--dry-run`: push 하지 않고 검사·리뷰·본문·판정까지(CI 는 안 봄).
- `--no-review`: 리뷰 에이전트를 건너뜀(본문은 `.git/pr-pipeline/<브랜치>.md` 에 직접).
- 기록: `.git/pr-pipeline/<브랜치>.json` (저장소 밖이라 커밋되지 않음).
- 끝나면 사용자에게 판정 한 줄 + 이유 + PR 링크를 알린다. 사람이 볼 것만 골라 보낸다.

셀프 테스트: `python scripts/test_pr_pipeline.py` — 가짜 원격 저장소·가짜 `claude`·가짜 `gh` 로 판정 경로 35가지와 직접 확인 3가지.

## 실제로 돌려 보고 막은 것

- **저장소 훅이 리뷰 세션에도 돈다**: 세션 기록 훅(SessionEnd)이 headless 리뷰 세션 내용을 기능 브랜치에 커밋했다. 리뷰 에이전트는 `--setting-sources user` 로 띄운다(사용자 가드 훅은 그대로). 그래도 리뷰 중 `review:` 가 아닌 커밋이 생기면 질문이 된다.
- **CLI 로그인 만료**: `claude -p` 가 1턴·토큰 0으로 끝났다. `is_error` 의 원문을 그대로 보여 주고, 로그인 문제면 `claude` → `/login` 을 안내한다.
- **리뷰 에이전트가 `.git` 아래에 못 쓴다**: 본문 경로가 `.git/pr-pipeline/` 이라 Claude Code 가 쓰기를 막았고, 파이프라인은 지난 실행의 본문으로 조용히 통과했다. 에이전트는 임시 폴더(`--add-dir`)에 쓰고 파이프라인이 옮긴다. 리뷰 전에 옛 본문을 지워, 이번 리뷰가 안 쓴 본문은 통과하지 못한다.
- **리뷰어에게 셸이 있었다**: `Bash(python:*)`·`Bash(node:*)` 를 허용해 두어 파이썬으로 `git push` 를 부를 수 있었다(리뷰어가 스스로 질문으로 남김). 지금은 Bash·웹을 모두 막고 Read·Grep·Glob 과 임시 폴더 한정 쓰기만 준다. 쓰기 규칙은 `Edit(//c/<경로>/**)` 형식이어야 먹었다(`Write(...)`·`//C:/`·`/C:/` 는 거부 — 실험). 모드는 `default`: `-p` 에서 허용 밖은 전부 거부된다.
- **Door 가 실행마다 바뀌었다**: 같은 PR #28 을 리뷰어가 one-way("공개 저장소라 머지가 곧 게시") 두 번, two-way 두 번으로 적었다. 같은 diff 에 옛 방식(한 번에 판단)만 따로 6번 물으면 6/6 two-way — 이 코드가 실제로 push·PR 댓글을 하는데도 놓쳤다. 지금은 판정을 떼어 내고 "머지 행위가 아니라 머지된 코드가 실행될 때 하는 일"을 항목별로 묻는다. 측정: PR #28 diff 3명×2묶음 모두 one-way, 표 `outbound 3/3·publishing 3/3·external_state 3/3` 동일. 문서만 바꾼 diff 는 두 묶음 모두 two-way, 표 0.
- **리뷰어가 "테스트를 돌렸는지 확인 못 함"을 물었다**: 리뷰어는 검사 출력 끝 3줄만 받았고, `check_skills.py` 는 성공하면 `ok: 16 skills checked` 한 줄뿐이라 셀프 테스트를 돌렸다는 흔적이 없었다. 지금은 검사 출력 끝 4000자를 넘기고(실행 기록 JSON 에는 끝 3줄만), `check_skills.py` 가 통과한 셀프 테스트를 한 줄씩 찍는다.
- **수정안 경로 실제 시연**: `.claude/skills/` 파일에 이력 주석 한 줄을 넣은 브랜치로 dry-run — 리뷰어가 수정안 파일을 쓰고 파이프라인이 `review: remove history comment above last_json` 으로 커밋, 검사 다시 통과. 권한 거부 0건.
- **비공개 함수 호출**: 리뷰 에이전트가 `check_pr_body._scan` 직접 호출을 질문으로 남겼다. 공개 함수 `scan_signals` 로 바꿨다.
- **`.claude/` 아래는 리뷰어가 못 고친다**: Claude Code 가 보호 폴더 편집을 거부하고, `--allowedTools "Edit(.claude/**)"` 로도 풀리지 않았다(작은 저장소로 실험). 그래서 리뷰어는 수정안 파일만 쓰고 파이프라인이 적용·커밋한다 — `.claude/` 아래도 고쳐진다. 거부된 도구 호출(`permission_denials`)은 파일 이름·명령과 함께 질문이 된다.
- **리뷰어가 검사를 120초 안에 못 끝냄**: Bash 기본 시간 제한. 지금은 리뷰어가 검사를 돌리지 않는다 — 리뷰 전 검사 출력을 파일로 받아 Evidence 에 쓰고, 수정안 적용 뒤 검사는 파이프라인이 돌린다.
- **리뷰어가 검사를 환경 변수 없이 돌림**: `CI=1` 없이 돌린 `check_skills.py` 가 설치본 불일치로 실패하자 "검사 실패"를 질문으로 남겼다. 프롬프트의 검사 목록에 `check_env` 를 붙인다. 거부된 Bash 는 명령까지 적는다.

## 하지 않는 것

- force push, 기록 다시 쓰기. 리뷰 커밋을 되돌릴 때도 revert.
- one-way 변경을 자동 머지. 설정으로도 못 켠다.
- 리뷰 에이전트에게 셸·웹·저장소 쓰기 권한을 주는 것.
- 판정을 사람 승인 대신으로 쓰는 것(`auto_merge` 를 켠 저장소에서만, 조건을 다 맞은 two-way 만).
