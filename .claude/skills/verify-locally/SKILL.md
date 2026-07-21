---
name: verify-locally
description: After changing a locally-run server (FastAPI/Flask/Express/etc.), actually start it and hit the affected endpoint(s) to confirm the change works — instead of claiming "fixed" from reading the diff alone. Use a scratch port, write non-ASCII request bodies to a file first (shell argument encoding silently mangles them), and clean up any test data/log files/processes afterward.
---

# Verify Locally

코드를 고친 뒤 "고쳤다"고 말하기 전에, 실제로 로컬 서버를 띄워서 그 변경이 진짜 동작하는지 확인합니다.

## 왜 이 스킬이 필요한가

- 코드를 읽고 "이론상 맞다"고 판단하는 것과, 실제로 서버를 띄워서 API가 그렇게 응답하는지 확인하는 것은 다릅니다.
  실제로 겪은 버그들(카테고리 매칭 오류, 시간대 변환 오류, 필드 기본값 누락) 전부 diff만 봐서는 안 보이고
  직접 호출해봐야 드러났습니다.
- 이미 다른 프로세스가 떠 있는 포트에 그대로 테스트하면 바인딩이 실패하거나, 실사용 데이터에
  테스트 데이터가 섞여 들어갑니다.
- 셸(Git Bash 등)로 한글/비ASCII 텍스트를 커맨드라인 인자에 직접 넣으면 인코딩이 깨져서,
  진짜 버그가 아닌데 "버그처럼 보이는" 가짜 에러가 납니다. 이 함정에 반복해서 걸리면 정작
  확인해야 할 실제 문제를 놓치게 됩니다.

## 절차

1. 기본 포트를 그대로 쓰지 말고, 확실히 비어있는 스크래치 포트를 골라서 그 위에 서버를 띄우세요
   (예: 기본이 8000이면 8090 같은, 지금 아무것도 안 쓰고 있는 포트).
2. 서버가 뜨면, 이번에 고친 부분과 직접 관련된 엔드포인트/기능을 실제로 호출해서 확인하세요.
   관련 없는 것까지 전부 확인할 필요는 없습니다.
3. 요청 바디에 한글 등 비ASCII 문자가 들어가면 커맨드라인에 직접 넣지 말고, 파일로 써서
   `--data-binary @file` 같은 방식으로 전달하세요.
4. 확인 중 만든 테스트 데이터(행, 레코드, 파일)는 검증이 끝나면 반드시 지우세요 —
   실사용 DB/상태를 오염시키면 안 됩니다.
5. 띄운 테스트 서버 프로세스를 종료하고, 만든 임시 로그/파일도 정리하세요.
6. 이 모든 과정을 거친 뒤에만 "확인했다/고쳤다"고 보고하세요. 확인 못 했다면 그렇다고
   명시하세요 — 안 해보고 됐다고 말하지 마세요.

## 하지 않는 것

- diff만 읽고 "동작할 것"이라고 단정하지 않기
- 이미 사용 중인 포트에 억지로 재사용/충돌 유발하지 않기
- 테스트 데이터를 실사용 DB에 남겨두지 않기
- 검증에 실패했는데 성공했다고 보고하지 않기
