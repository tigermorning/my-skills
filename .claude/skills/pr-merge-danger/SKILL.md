---
name: pr-merge-danger
description: Write a PR body (or a worker's merge report) that lets a human decide in seconds how hard to review it - Summary as the smallest picture (pseudocode, call tree, file tree, mermaid), Evidence from actually running it, and a Merge Danger call (Door - one-way or two-way; Blast radius - one word). Use when opening or describing a PR, when an orchestrator merges agent branches, when PRs pile up unreviewed, or when deciding which agent changes a human must read in full. One-way doors (data loss, migrations, outbound messages, publishing, secrets, public contracts) always get a full human review; two-way doors with a small radius get a light one. Bundles check_pr_body.py, which fails a body missing these parts and flags one-way signals in the diff.
---

# PR Merge Danger — 사람이 볼 PR을 고르는 본문

사람 리뷰가 병목인 이유는 사람이 느려서가 아니라, 모든 PR을 같은 강도로 보기 때문이다.
대부분의 변경은 머지한 뒤에도 되돌릴 수 있다(two-way door).
되돌릴 수 없는 것(one-way door)만 사람이 끝까지 보면 된다.
PR 본문이 그 판단을 대신 정리해 준다.

출처: Matt Pocock, "Fixing the PR Bottleneck"(AI Engineer Paris 2026)의 PR 원칙과
공개 `pr` 스킬의 본문 구조(Summary → Evidence → Merge Danger)를 일반화.

## 인식 신호

- PR을 열거나 본문을 쓴다.
- 오케스트레이터가 일꾼 브랜치를 합치기 전에 보고서를 읽는다.
- 리뷰 안 된 PR이 쌓인다. 어떤 것을 사람이 꼭 봐야 하는지 모르겠다.
- "작은 변경이니 괜찮겠지"라는 말이 나온다 — 작아도 one-way일 수 있다.

## 본문 형식

```markdown
## Summary
<!-- 가장 작은 그림 하나 + 짧은 설명. 긴 글 금지. -->

## Evidence
<!-- 실제로 돌려 본 결과. 화면 변화는 스크린샷, 그 외는 명령과 출력 한 줄. -->

## Merge Danger
**Door:** <one-way | two-way>
**Reason:** <한 줄>
**Blast radius:** <한 단어>
```

- `<…>` 칸과 `<!-- -->` 주석은 채우지 않으면 검사기가 실패로 본다. 틀을 그대로 내면 통과하지 않는다.
- 한국어 제목(`## 요약` / `## 증거` / `## 머지 위험`, `문:` / `이유:` / `영향 범위:`)도 검사기가 읽는다.
- 절 안에 소제목(`### Call tree`, `### Door`)을 써도 된다. 같거나 얕은 제목이 나와야 절이 끝난다.

### Summary — "왜·무엇"을 가장 빨리

변경 성격에 맞는 가장 작은 그림 하나를 고른다.

| 변경 | 그림 |
|---|---|
| 로직·알고리즘 | 의사코드 |
| 실행 흐름 | 호출 트리 |
| UI 구조 | 컴포넌트 트리(상태·경계 표시) |
| 파일 책임 이동·리팩터 | 파일 트리 |
| 여러 주체의 상호작용 | mermaid sequence |
| 기존 모양 안의 작은 수정 | diff 조각 |

- 그림 옆에 그 그림이 답하는 짧은 문장만 둔다.
- 질문에 필요한 호출·파일·상태만 남기고 나머지는 지운다.

### Evidence — 읽은 것 말고 돌려 본 것

- 화면이 바뀌면 전후 스크린샷이 가장 강하다.
- 그 외에는 실행한 명령과 관찰한 출력 한 줄(테스트 개수, 응답 코드, 로그).
- 절차는 [[verify-by-running]]을 따른다. 못 한 검증은 "건너뜀: 무엇, 왜"로 적는다.
- 마지막 커밋(리뷰 커밋 포함) 기준으로 돌린 결과를 적는다. 리뷰어가 고친 뒤의 증거가 없으면 다시 돌린다.

### Merge Danger — 리뷰 강도를 정하는 두 줄

**Door** — 머지 후 되돌리기만 하면 원상복구 되는가?

- two-way: revert 하나로 끝. 대부분의 PR.
- one-way: revert해도 이미 일어난 일이 남는다.
  - 데이터 삭제·마이그레이션·스키마 변경
  - 밖으로 나가는 것: 메일·알림·웹훅·결제·외부 API 쓰기
  - 공개·배포: push, publish, 배포 파이프라인, 게시
  - 비밀값·권한·인증 설정
  - 다른 사람이 기대는 계약: 공개 API, 파일 형식, 저장 데이터 형식
- 한 줄짜리 변경이어도 수만 명에게 메일이 나가면 one-way다. 크기로 판단하지 않는다.

**Reason** — Door를 그렇게 본 이유 한 줄. 특히 diff에 one-way 신호가 있는데 two-way라고 할 때 꼭 쓴다.

**Blast radius** — 잘못되면 어디까지, 얼마나 나쁜가. 한 단어로.

- 예: `localized`(한 화면·함수) · `module` · `app` · `users` · `data` · `external`

**리뷰 강도**

| Door | Blast radius | 사람 리뷰 |
|---|---|---|
| one-way | 무엇이든 | 전부 읽는다. 승인 전 머지 금지 |
| two-way | localized / module | Summary·Evidence만 훑고 머지 |
| two-way | app 이상 | Summary·Evidence + 위험한 파일만 |

## 검사기

```bash
python scripts/check_pr_body.py body.md --diff changes.diff
```

```bash
python scripts/check_pr_body.py --gh 123              # 본문은 gh pr view, diff는 gh pr diff
```

- diff 파일은 UTF-8로 만든다: `git diff --output=changes.diff main...HEAD`.
  - PowerShell의 `git diff > f`는 UTF-16으로 저장된다. 검사기는 UTF-16·NUL이 든 파일을 종료 코드 2로 거부한다.
- 실패(종료 코드 1):
  - 세 절이 없거나, 비었거나, `TODO`·`<…>` 칸·HTML 주석뿐이다.
  - `Door:`가 one-way/two-way 중 하나가 아니다. 둘 다 적어도 실패.
  - `Blast radius:`가 비었다.
- 코드 블록(```` ``` ````·`~~~`) 안의 줄은 제목·칸으로 보지 않는다.
- one-way 신호 — 힌트일 뿐이다. 신호가 없다고 two-way라는 뜻은 아니다.
  - 내용 신호: diff의 `+`/`-` 줄에서만 찾는다. 문서(`.md`·`.txt`·`.rst`)는 뺀다.
    DROP/ALTER/TRUNCATE(INDEX 포함), DELETE FROM, 메일·웹훅 보내기, git/docker push·npm publish·gh release create, terraform/kubectl apply, rm -rf·os.remove 등 파일 삭제.
  - 경로 신호: diff 머리 줄의 경로에서만 찾는다.
    `migrations/`·`db/migrate/`·`alembic/versions/`, `.github/workflows/`·`deploy/`·`deploy.*`, `.env*`(`.env.example` 제외), `openapi*`·`*.proto`·`schema*`.
  - two-way라고 적었는데 신호가 있으면 경고하고, `Reason:` 칸이나 Door 줄 괄호 안 이유가 없으면 실패.
- 출력 첫 줄 `review=full|light`가 사람의 리뷰 강도다.
- 파일이 없거나 `gh`가 없으면 종료 코드 2. 본문 파일과 `--gh`를 함께 주면 종료 코드 2.

### CI·합치기 관문에 걸기

- GitHub Actions: PR 이벤트에서 `python check_pr_body.py --gh ${{ github.event.pull_request.number }}`. 실패하면 본문 없는 PR이 사람에게 오지 않는다.
- [[worker-merge-gate]]의 빠른 검사(`quick`)에는 바로 걸 수 없다.
  - `quick` 명령에는 카드 번호·보고서 경로가 넘어가지 않는다.
  - 일꾼 보고서 틀(한 것 / 확인 / 막힌 것 / 합칠 때 주의)은 이 세 절과 다르다. 그대로 검사하면 Summary·Merge Danger가 없다고 실패한다.
  - 쓰려면 보고서 틀에 `## Summary`·`## Merge Danger`를 더하고(확인 칸은 Evidence로 읽힌다), 오케스트레이터가 합치기 전에 손으로 돌린다:
    `git diff --output=changes.diff main...worker/T-012` 뒤 `python check_pr_body.py docs/reports/T-012.md --diff changes.diff`.

셀프 테스트: `python scripts/test_check_pr_body.py`

## 하지 않는 것

- Merge Danger를 "낮음/중간/높음" 같은 느낌 점수로 쓰지 않는다. 되돌릴 수 있는지와 범위로 쓴다.
- 증거 없이 "테스트 통과"라고만 쓰지 않는다. 명령과 숫자를 쓴다.
- two-way라고 리뷰를 건너뛴 PR이 문제를 일으키면, 판단 기준을 [[review-retro]]로 고친다.
