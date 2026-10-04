---
name: pr-pipeline
description: Run a finished feature branch through the whole PR pipeline so a person only reads the PRs that need one - repo checks, a headless review agent (claude -p) that commits sure fixes and leaves questions and writes the PR body, the pr-merge-danger body check against the real diff and the user's one-way rules, push and PR, CI, then a merge verdict. Auto-merges only when the repo opted in and every condition holds (checks and CI green, two-way door, no one-way signal, no review question, small, no protected path); otherwise the PR stays open with the reasons as a comment. Use when an agent finishes work on a branch, when the user says to open or ship a PR, when agent PRs pile up, or when setting up "humans only review one-way doors" for a repo. Needs <repo>/.claude/pr-pipeline.json.
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
preflight ─▶ checks ─▶ review(claude -p) ─▶ checks again ─▶ body check ─▶ push·PR·CI ─▶ verdict
  깨끗한가     실패면 멈춤   고쳐서 커밋·질문·본문   깨지면 리뷰 커밋 revert   pr-merge-danger      (--dry-run 은 생략)   자동 머지 / 사람에게
```

| 단계 | 하는 일 | 멈추는 때 |
|---|---|---|
| preflight | 기준 브랜치가 아닌지, 작업 트리가 깨끗한지, 앞선 커밋이 있는지 | 하나라도 아니면 종료 코드 2 |
| checks | 설정의 `checks` 명령을 차례로(환경변수는 `check_env`) | 실패면 종료 코드 1, 리뷰는 안 돎 |
| review | 사람 없이 리뷰 에이전트. 공통 규칙·저장소 규칙으로 보고, 확실한 것만 원래 바뀐 파일 안에서 `review:` 커밋, 나머지는 질문, PR 본문을 씀. push·reset·rebase·checkout·웹은 막힘 | 커밋 안 한 변경을 남기면 종료 코드 1 |
| checks again | 리뷰 커밋 뒤 다시 | 깨지면 리뷰 커밋을 `git revert` 하고 질문으로 남김 |
| body | `check_pr_body.py`: 세 절, Door, 실제 diff 의 one-way 신호, 사용자 공통 위험 목록 | 본문이 없으면 종료 코드 1 |
| publish | push, PR 만들기 또는 본문 갱신, CI 기다림 | — |
| verdict | 아래 조건 | — |

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

셀프 테스트: `python scripts/test_pr_pipeline.py` — 가짜 원격 저장소·가짜 `claude`·가짜 `gh` 로 판정 경로 22가지.

## 실제로 돌려 보고 막은 것

- **저장소 훅이 리뷰 세션에도 돈다**: 세션 기록 훅(SessionEnd)이 headless 리뷰 세션 내용을 기능 브랜치에 커밋했다. 리뷰 에이전트는 `--setting-sources user` 로 띄운다(사용자 가드 훅은 그대로). 그래도 리뷰 중 `review:` 가 아닌 커밋이 생기면 질문이 된다.
- **CLI 로그인 만료**: `claude -p` 가 1턴·토큰 0으로 끝났다. `is_error` 의 원문을 그대로 보여 주고, 로그인 문제면 `claude` → `/login` 을 안내한다.

## 하지 않는 것

- force push, 기록 다시 쓰기. 리뷰 커밋을 되돌릴 때도 revert.
- one-way 변경을 자동 머지. 설정으로도 못 켠다.
- 리뷰 에이전트에게 push·웹 권한을 주는 것.
- 판정을 사람 승인 대신으로 쓰는 것(`auto_merge` 를 켠 저장소에서만, 조건을 다 맞은 two-way 만).
