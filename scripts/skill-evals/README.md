# skill-evals — 스킬 유닛 테스트

스킬이 실제로 결과를 바꾸는지 확인하는 eval 모음이다.
Lauren Tan(Cursor)의 "eval은 스킬의 유닛 테스트" 방식을 따랐다.

## 구성

| 위치 | 내용 |
|---|---|
| `.claude/skills/<스킬>/evals/evals.json` | 과제 프롬프트, 기대 결과, 채점 항목 |
| `.claude/skills/<스킬>/evals/fixtures/` | 과제에 쓰는 입력 파일 (서버, CSV, 기사 등) |
| `scripts/skill-evals/grade.py` | 기계 채점 스크립트 (파일 결과 + transcript 순서) |

채점 항목의 `check` 값은 세 가지다.

- `script`: `grade.py`가 산출물을 직접 실행해서 채점한다. 보류 입력 세트를 쓴다.
- `transcript`: 도구 호출 기록을 보고 순서·방식을 채점한다.
- `judge`: 다른 모델이 설정을 모르는 상태(blind)로 보고서와 산출물을 읽고 채점한다.

## 돌리는 법

1. 과제마다 작업 폴더를 만든다. 폴더 이름은 `jobs/j01`처럼 중립적으로 짓는다.
   - 에이전트가 평가받는다는 걸 알면 행동이 달라진다.
2. 설정 세 가지로 돌린다.
   - **skill**: 프롬프트 앞에 "SKILL.md를 읽고 따르라"를 붙인다.
   - **desc_only**: 이 저장소 안에서 서브에이전트로 실행한다. 스킬 본문은 읽지 않지만, 스킬 설명은 시스템 프롬프트에 자동으로 들어간다.
   - **clean_baseline**: 저장소 밖 폴더에서 `claude -p`로 실행한다. 스킬이 전혀 없는 상태다.
   ```bash
   cd <작업 폴더> && claude -p --model sonnet --permission-mode bypassPermissions --output-format stream-json --verbose < prompt.txt > transcript.jsonl
   ```
3. 채점한다.
   ```bash
   python scripts/skill-evals/grade.py <eval-name> <작업 폴더> <transcript.jsonl>
   ```
4. `judge` 항목은 다른 모델에게 blind로 맡긴다.
   - 보고서에서 스킬 이름과 폴더 경로를 가린 뒤 넘긴다.

## 결과 (2026-09-24, 실행 모델 Sonnet, 심판 Opus)

### 1회차 — 6개 과제 × 3개 설정

| 과제 | skill | desc_only | clean_baseline |
|---|---|---|---|
| curl-create-korean-note | 3/3 | 3/3 | 2/3 |
| misdiagnosed-parse-error | 3/3 | 3/3 | 2/3 |
| phone-normalizer-real-csv | 5/6 | 2/6 | 2/6 |
| sentence-splitter-real-news | 5/5 | 5/5 | 4/5 |
| korean-particle-euro-ro | 2/4 | 2/4 | 2/4 |
| english-pluralize | 4/4 | 2/4 | 2/4 |
| **합계** | **22/25 (88%)** | **17/25 (68%)** | **14/25 (56%)** |

### 1회차에서 배운 것

- 스킬 설명만 보여도 효과가 있다. 설명만 보인 경우(desc_only)가 스킬이 없는 경우보다 12%p 높았다.
- clean_baseline의 대표적인 실패:
  - 원인은 맞게 진단하고도 멀쩡한 `server.py`에 cp949 fallback을 넣었다.
  - 한글을 curl 인자에 직접 넣었다가 400 오류를 받고 나서야 방법을 바꿨다.
- `real-world-review-cycle`의 차이가 가장 컸다.
  - 스킬 없이도 버그는 찾았지만, 고치지 않고 보고만 했다.
  - 버그와 판단이 필요한 사례를 구분하지 않았다.
- `verify-then-code`의 약점:
  - 세 설정 모두 숫자로 끝나는 입력("3으로", "1로")을 틀렸다.
  - 정답표를 코드 파일의 docstring에 함께 써서, 표가 코드보다 먼저 만들어지지 않았다.

### 2회차 — `verify-then-code` 개정 후 skill 설정만 재실행

- 개정 내용:
  - 1단계에 "규칙이 전제하는 범위 밖의 입력"을 따로 나열하도록 추가했다.
  - 2단계에 "정답표는 별도 파일로"를 추가했다.
- 결과: 기계 채점 항목 기준 4/6 → 11/12. 과제별로 2번씩 돌렸다.
  - 숫자 입력은 정답을 내거나 명시적 예외(ValueError)로 처리했다. 틀린 답을 낸 경우는 0건이다.
  - 남은 실패 1건: 정답표를 여전히 코드 안의 dict로 둔 경우.
- judge 항목은 2회차에 다시 채점하지 않았다.

## 한계

- 과제당 실행 횟수가 1~2회라 분산을 추정할 수 없다.
- 실행 모델이 Sonnet 하나뿐이다. 다른 모델에서의 결과는 모른다.
- `table-before-code` 판정은 파일 이름 휴리스틱(table/answer/test_)에 의존한다.
- `non-ascii-via-file`의 6단계("서버를 고치지 마라")는 eval 이후에 추가했다. 아직 재검증하지 않았다.
