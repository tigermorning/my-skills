---
name: worker-merge-gate
description: Install a merge gate in a repo where agent workers each build one task on their own branch and an orchestrator merges them — a git hook that, when a worker branch is merged into a guarded branch, checks that the worker only touched the files its task card lists (or named the others in its report), that the report has every required section, and that a quick check passes, and refuses the merge commit otherwise. Use when setting up or tightening an orchestrator/worker pipeline, when rules like "only touch your card's files" or "run the checks before merging" live only in documents, when a person keeps reviewing worker diffs for scope by hand, or when porting an existing gate to another project. Includes the kit (scope_check.py, merge_gate.py), a config template, a retro mode that replays past merges to calibrate before trusting the gate, and a self-test of every way in it must block.
---

# Worker Merge Gate

일꾼(에이전트)이 카드 하나씩 자기 브랜치에서 만들고 오케스트레이터가 합치는 저장소에 **합치기 관문**을 깐다.
말로만 있던 규칙("카드의 파일만 고친다", "보고서를 채운다", "합치기 전에 검사한다")을 사람이 diff를 읽기 전에
git 훅이 기계로 판정한다. 관문은 하드 강제(훅)이고, 이 스킬은 그것을 프로젝트에 맞게 까는 절차다.

## 왜 필요한가

- 일꾼이 늘수록 오케스트레이터가 diff를 읽으며 "범위 밖이네"를 잡는 일이 병목이 된다.
- 문서 규칙은 에이전트가 잊는다. 훅은 잊지 않는다. 규칙 문서·스킬은 소프트 강제, 훅·CI는 하드 강제다
  (Lauren Tan, Cursor — "에이전트를 믿게 만드는 법"의 강제 수단 층).

## 인식 신호

- 일꾼 브랜치 이름에 카드 번호가 있다(`worker/T-012` 등). 카드에 "만지는 파일" 목록이 있다.
- 일꾼이 보고서를 정해진 틀로 쓴다.
- "합치기 전에 검사 초록" 같은 관문이 문서에만 있다.

앞의 둘이 없으면 관문을 깔기 전에 카드 틀·보고서 틀부터 만든다. 판정할 기준이 없으면 관문은 아무것도 못 본다.

## 절차

### 1. 먼저 확인

- 오케스트레이터 세션이 지금 그 저장소에서 합치고 있으면 **직접 깔지 않는다**. 따로 worktree·브랜치에서 만들고, 보고서와 함께 오케스트레이터에게 넘긴다. 일하는 중에 관문이 생기면 그쪽 merge가 이유도 모른 채 막힌다.
- 바꿀 검사 파일·문서가 다른 일꾼 카드의 "만지는 파일"과 겹치는지 본다. 겹치면 그 카드 다음 차례로 합친다.

### 2. 키트 넣기

- 이 스킬의 `scripts/scope_check.py`·`scripts/merge_gate.py` 를 프로젝트의 `.merge-gate/` 에 복사한다.
- `scripts/config.example.json` 을 `.merge-gate/config.json` 으로 복사해 채운다.

| 설정 | 뜻 |
|---|---|
| `guarded_branch` | 되짚기가 볼 브랜치. 훅은 설치한 worktree 의 브랜치를 지킨다 |
| `project_dir` | 저장소 안 프로젝트 폴더. 그 밖을 고치면 엄격 판정 |
| `worker_branch` · `card_id` | 일꾼 브랜치 → 카드 번호(1번 그룹) · merge 메시지에서 번호 찾기 |
| `card.path` · `card.ref` | 카드 파일. 저장소 안 경로면 **합칠 대상 브랜치의 판**으로 읽는다(일꾼이 자기 카드를 넓혀도 판정이 따라가지 않게). 카드가 다른 브랜치·저장소에 있으면 `ref`(예: `<브랜치>:<경로>`)로 커밋본을 가리킨다 |
| `card.section` · `card.ban` · `card.strip` | 만지는 파일 칸 제목 · 금지 불릿·하위 제목 머리 · 카드가 다른 기준으로 쓴 경로 앞부분 |
| `aliases` | 카드에 말로만 쓴 금지어의 뜻. 정하지 않은 말은 "기계로 못 봄"으로 알린다 |
| `report.sections` · `report.strict` · `report.numbers_in` | 보고서 필수 칸 · 금지·바깥 파일을 적어야 하는 칸 · 숫자가 있어야 하는 칸 |
| `judges` | 판정기 파일. 바뀌면 카드 안이어도 △ |
| `quick` | 빠른 검사 명령. `{head:경로}` 는 HEAD 판을 임시 폴더에 꺼내 쓴다 · `{python}` · `{repo}` |

- 빠른 검사는 **몇 분 안**이어야 한다. 화면 검사처럼 오래 걸리는 것은 빼고, 합친 뒤 따로 돌린다.
- 빠른 검사 스크립트가 자기 파일 위치로 저장소를 찾으면 `{head:…}` 로 임시 폴더에서 돌 때 틀린다. 저장소 경로를 인자(`--repo={repo}` 등)로 받게 고친다.
- 키트와 설정을 **커밋한다**. 관문은 HEAD 판으로 판정하므로, 커밋 전에는 설치가 거부된다.

### 3. 처음 믿기 전에 되짚기

```bash
python .merge-gate/scope_check.py --retro --soft
```

- 지난 일꾼 합치기 전부를 지금 판정기로 다시 판정한다. ✘ 마다 보고서·카드 원문을 열어 본다.
  - **판정기 결함**(같은 뜻을 다른 꼴로 썼음 — 콜론 없는 칸 머리, 짝 파일 `x.png`+`x.json`, 글롭으로 적은 이름 등): 판정기나 설정을 고친다.
  - **실제 누락**(보고서에 파일 경로가 없음): 고치지 않고 그대로 둔다. 관문이 잡아야 할 것이다.
  - **옛 틀**(지금 틀에 있는 칸이 그때는 없었음): 무시한다. 관문은 앞으로의 합치기에만 걸린다.
- 프로젝트마다 문서 쓰는 버릇이 달라 **새 프로젝트에서는 새 오탐이 나온다**. 되짚기를 건너뛰면 관문이 일꾼을 괜히 막는다.
- 작업 중에 새로 합쳐진 실제 건이 있으면 그것에도 한 번 더 돌린다.

### 4. 설치

```bash
python .merge-gate/merge_gate.py --install   # 지킬 브랜치에 있는 worktree 에서
python .merge-gate/merge_gate.py --status    # "✔ 관문 켜짐(<브랜치>)"
```

- `--status` 줄을 프로젝트의 검사 표(CI·전체 검사 스크립트 등)에 넣는다. 훅은 git으로 안 옮겨져서, 다른 PC·새 worktree에서 조용히 꺼져 있을 수 있다.
- 설치는 지킬 브랜치의 merge 기본을 `--no-ff` 로 바꾼다. fast-forward는 훅을 안 부르기 때문이다. 명령줄 `--ff-only` 는 그대로 앞선다.
- 훅 폴더를 여러 worktree가 함께 쓰면(전역 `core.hooksPath` 없음) 설치할 때마다 지키는 브랜치가 목록에 더해진다. 전역 `core.hooksPath` 가 `_dispatch` 중계 폴더면 worktree마다 따로 깐다. 다른 도구(husky 등)의 폴더면 설치가 멈추고 잇는 법을 알려 준다. 남의 훅은 덮지 않는다.
- 브랜치 이름이나 python 경로에 작은따옴표 같은 셸 특수 글자가 있으면 설치를 거부한다.

### 5. 시험

- 키트 셀프 테스트: `python <이 스킬>/scripts/test_merge_gate.py` — 임시 저장소에서 아래를 모두 확인하고 지운다.
- 프로젝트에서도 임시 worktree·임시 브랜치로 한 번 더(끝나면 worktree·브랜치·가짜 원격 ref·`branch.<임시>` 설정까지 지우고 남은 것 0을 확인):

| 시험 | 기대 |
|---|---|
| 일꾼이 아닌 브랜치 merge · 원격에서 받는 평범한 `git pull` | 통과 |
| 카드 밖 수정 + 보고서에 없음 | 막힘, HEAD 그대로, `merge --abort` 로 깨끗 |
| 이름으로 숨기기: 같은 이름의 태그, `refs/heads/…`, `origin/worker/…`, `@{-1}`, (Windows) 대소문자 | 막힘 |
| `git pull --no-rebase [-X theirs] . worker/…` | 막힘 |
| `--squash --ff` 뒤 commit | 막힘 |
| 일꾼이 판정기를 `exit(0)` 으로 바꾸고 위반 · 자기 카드에 금지 파일을 허용으로 옮김 | 막힘(HEAD 판·대상 브랜치 판이 판정) |
| 범위는 맞는데 빠른 검사 실패 | 막힘 |
| 충돌 → 풀고 `git commit`(메시지에 다른 브랜치 이름을 적어도) | 막힘(pre-commit 경로) |
| fast-forward 될 일꾼을 `--no-ff` 없이 | 막힘 |
| 다른 worktree에서 설치한 뒤에도 처음 브랜치 | 계속 막힘 |
| 정상 일꾼 | 통과(걸린 시간을 적어 둔다) |
| 보통 커밋 | 통과, `merge-gate.running` 남지 않음 |

- 시험 브랜치를 만들 때 커밋 안 한 작업 파일이 `git add` 에 딸려 가지 않게 한다. 임시 브랜치를 지우면 함께 사라진다(되살리려면 reflog).

### 6. 문서와 넘기기

- 하네스 문서(HARNESS·README 등)의 관문 절에 적는다: 무엇을 막나, 설치 명령, `--status`, 건너뛰기(`--no-verify`)는 사람이 허락할 때만.
- 일꾼 지침에 한 줄: 보고하기 전에 `scope_check.py --worktree --soft` 로 ✘ 가 없는지 본다(커밋 안 한 파일까지 본다).
- 다른 자동화(자동 저장 커밋 등)가 같은 worktree에서 돌면, 관문이 도는 동안 git-dir 에 있는 `merge-gate.running` 을 보고 건너뛰게 한다.

## 판정 규칙(요약)

- 카드 안 → ✔. 카드 밖은 막지 않고 **보고서에 적었나**로 가른다(정당한 범위 밖 수정이 많다).
  - 목록에 없는 파일: 보고서 어디든 이름(확장자 뺀 이름·글롭·같은 폴더의 짝 파일 포함)이 있으면 △
  - 금지 파일·프로젝트 폴더 밖: `report.strict` 칸에 경로가 있어야 △ — 지나가며 쓴 이름은 안 침
  - 이름은 통째로 맞춘다(`unlocked.mjs` 가 `locked.mjs` 를 대신하지 않는다)
  - 아니면 ✘
- 판정기 파일 변경은 늘 △. 시험 파일 `x.test.*` 는 짝 모듈이 카드에 있으면 카드 안.
- 보고서 칸 빠짐·확인 칸에 숫자 없음 → ✘. 칸은 제목이거나, 첫 소제목 앞의 불릿, 또는 `- 칸이름:` 꼴 불릿이다(본문 불릿은 칸이 아니다).

## git 함정 — 관문이 이렇게 생긴 이유

| 함정 | 대응 |
|---|---|
| 충돌 없는 `git merge` 의 `pre-merge-commit` 시점엔 `MERGE_HEAD` 가 아직 없다 | 들어오는 이름은 `GIT_REFLOG_ACTION`("merge <이름…>"), pull 은 `FETCH_HEAD` 의 합칠 줄에서 읽는다 |
| 충돌을 풀고 `git commit` 하면 `pre-merge-commit` 이 안 불린다 | 같은 판정을 `pre-commit` 에도. 보통 커밋은 `MERGE_HEAD` 가 없어 바로 통과 |
| fast-forward 는 어떤 훅도 안 부른다 | 지키는 브랜치에 `mergeOptions=--no-ff` |
| 이름은 속는다(태그, `@{-1}`, 대소문자, 직접 쓴 merge 메시지) | 이름과 상관없이 들어오는 커밋을 가리키는 `worker/` ref 를 `for-each-ref --points-at` 으로 찾는다 |
| 합친 작업 트리의 판정기·카드는 일꾼이 고친 판이다 | 판정기는 HEAD 판, 카드는 대상 브랜치 판(또는 `card.ref`)으로 |
| 훅 안에서 `GIT_DIR`·`GIT_INDEX_FILE` 이 걸려 있다 | 자식 git 에는 저장소 위치 변수를 지운다 |
| 한글 윈도에서 `python -` 은 파이프로 받은 스크립트를 콘솔 코드 페이지로 읽는다 | 훅은 HEAD 판을 바이트로 받아 `compile` 한다 |

## 관문이 못 보는 것

- cherry-pick · rebase(`git pull --rebase` 포함)로 옮기기 — merge 가 아니라 훅이 안 불린다. 파이프라인이 merge 만 쓰게 정해 둔다.
- 빠른 검사가 부르는 하위 검사들은 합친 쪽 판으로 돈다. 바뀌면 diff로 본다.
- 말로만 쓴 금지(`aliases` 에 없는 말)와 키트가 못 읽는 경로 — `·` 줄로만 알린다.
- 같은 커밋을 일꾼 브랜치와 원격 지키는 브랜치가 함께 가리키는 드문 경우, 원격 받기가 일꾼 합치기로 판정될 수 있다. 메시지를 보고 사람이 판단한다.
- 재미·느낌·디자인 판단 — 사람 감수 몫이다.

## 실패 사례 — 이 키트가 생긴 이유

- 첫 판 관문이 위반 브랜치를 그대로 합쳤다. 충돌 없는 merge 의 `pre-merge-commit` 에는 `MERGE_HEAD` 가 없는데, 그것만 보고 "일꾼 merge 아님"으로 판단했다. 훅 안에 탐침을 넣어 확인한 뒤 `GIT_REFLOG_ACTION` 을 읽게 고쳤다.
- 따로 띄운 리뷰어가 이름으로 숨기기·pull 인자·카드 넓히기·공유 훅 폴더 덮어쓰기 같은 우회를 실제 git 으로 재현했다. 모두 위 시험 목록과 셀프 테스트에 들어 있다.
- 두 번째 프로젝트로 옮기자 보고서 쓰는 버릇이 달라 오탐이 새로 나왔다. 그래서 되짚기를 절차의 필수 단계로 둔다.
