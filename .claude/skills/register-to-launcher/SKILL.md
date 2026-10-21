---
name: register-to-launcher
description: 지금 작업 중인 프로젝트를 "앱 관리 프로젝트"(앱 런처)에 앱 카드로 등록하거나 정보를 갱신한다. "앱 관리 프로젝트에 등록해줘", "이 프로젝트 런처 앱으로 등록해줘", "런처에 등록해줘", "런처 정보 업데이트해줘" 같은 요청에 사용.
---

# 런처에 등록하기

지금 프로젝트를 살펴 실행 방법을 정하고, 사용자에게 **한 번 확인받은 뒤** 런처 목록에 넣는다. 같은 프로젝트를 다시 등록하면 중복 없이 갱신된다(원본 폴더 기준).

## 0. 런처 위치 찾기

```bash
CONF="${MY_APP_LAUNCHER_HOME:-$HOME/.config/my-app-launcher}/config.json"
node -e "console.log(require(process.argv[1]).launcherDir)" "$CONF"
```

- 파일이 없거나 값이 비어 있으면 멈추고 알린다: "앱 관리 프로젝트가 설치되어 있지 않아요. 런처 저장소에서 `bash scripts/setup.sh`를 먼저 실행해 주세요."
- 아래에서 `<런처>`는 이 값이다.

## 1. 살펴보기 (읽기만 — 파일을 고치지 않는다)

프로젝트 루트(`git rev-parse --show-toplevel`, git이 아니면 현재 폴더)에서 다음을 읽는다.
- `README*` (첫 문단 → 설명 후보, 본문 속 `https://` 주소 → 배포 주소 후보)
- `package.json` (`name`, `description`, `scripts.start`·`scripts.dev`, `homepage`)
- `project.godot` (Godot 프로젝트인지)
- 실행 스크립트: `*.bat` `*.vbs` `*.ps1` `start.sh` `run.sh` (루트와 `scripts/`)
- 배포 설정: `vercel.json`, `.vercel/project.json`, `render.yaml`
- 정적 사이트인지: 루트나 `public/`·`dist/`의 `index.html`
- (`<런처>/scripts/import-shortcuts.mjs`가 있을 때만) 바탕화면 바로가기 중 이 프로젝트를 가리키는 것: `node <런처>/scripts/import-shortcuts.mjs --dry-run`의 결과에서 이름이 비슷한 항목

## 2. 실행 방법 고르기

후보가 여럿이면 아래 순서대로 추천하고 나머지도 보여 준다.

| 찾은 것 | 실행 방법 (`launch`) |
|---|---|
| 배포 주소(Vercel·Render 등) | `{ "type": "url", "url": "<주소>" }` |
| `project.godot` | `{ "type": "windows", "file": "<Godot exe Windows 경로>", "args": ["--path", "\\\\wsl.localhost\\<배포판>\\<프로젝트 경로, 역슬래시>"] }` — Godot 경로는 바탕화면 바로가기나 사용자에게서 얻는다 |
| Windows 실행 스크립트(`.bat` `.vbs` `.ps1`) | `{ "type": "windows", "file": "<Windows 경로>" }` |
| WSL에서 도는 서버·명령(`npm start`, `start.sh`) | `{ "type": "wsl", "command": "<명령>", "cwd": "<프로젝트 경로>", "window": "new" }` — 창을 보여 줄 필요 없으면 `"hidden"` |
| 빌드 없이 여는 정적 `index.html`만 | `{ "type": "local-web", "dir": "<index.html이 있는 폴더>", "entry": "index.html" }` |
| 크롬 앱으로 설치된 웹앱 | `{ "type": "chrome-app", "appId": "<32자>", "profile": "Default" }` — 바로가기에서 찾은 경우만 |

| 실행할 앱이 아니라 결과물(영상·문서·이미지)이 산출물인 프로젝트 | `{ "type": "file", "path": "<완성본 파일 경로, C:\\… 또는 /home/…>" }` — 기본 프로그램으로 연다. 완성본 위치는 사용자에게 묻고, 결과물 폴더도 `moreLaunches`에 `{ "label": "결과물 폴더", "launch": { "type": "file", "path": "<폴더>" } }`로 함께 담는다. 썸네일은 영상이면 ffmpeg로 한 장면을 뽑아 `thumbnailFile`로 |

배포판 이름은 `$WSL_DISTRO_NAME`이다.

## 3. 초안 만들기

```json
{
  "name": "<README 제목 또는 package.json name, 사람이 읽기 좋게>",
  "description": "<README 첫 문단 한 줄 요약, 300자 이하>",
  "category": "<게임·도구·에이전트·공모전 등 — 기존 분류가 있으면 그중에서>",
  "sourceDir": "<프로젝트 루트 절대 경로>",
  "launch": { ... },
  "launchLabel": "<실행이 여럿일 때만: 기본 실행 이름표>",
  "moreLaunches": [ { "label": "<이름표>", "launch": { ... } } ],
  "thumbnailFile": "<있으면: docs/images·screenshots·thumbs 등의 PNG/JPG/WEBP 절대 경로>"
}
```

기존 분류 목록은 `${MY_APP_LAUNCHER_HOME:-$HOME/.config/my-app-launcher}/apps.json`의 `category` 값들에서 본다.

## 4. 사용자에게 한 번 확인 (필수)

초안을 표(이름·설명·분류·실행 방법·원본 폴더·썸네일)로 보여 주고 "이대로 등록할까요? 고칠 점이 있으면 알려 주세요."라고 묻는다. **확인 없이 등록하지 않는다.** 고칠 점은 반영해 다시 보여 준다.

먼저 `--dry-run`으로 형식을 검사하고, 결과의 `action`(`added`=새로 추가 / `updated`=기존 카드 갱신)을 함께 알린다.
`updated`면 `target.name`(갱신될 카드 이름)도 알린다.

**한 프로젝트 = 카드 하나.** 한 프로젝트에서 실행이 여럿 나오면(배포 URL·로컬 실행·공개 모드, 크롬판·엣지판 등) 카드를 나누지 않고 한 카드에 담는다.
- 초안에 `"launchLabel": "<기본 실행 이름표>"`와 `"moreLaunches": [{ "label": "<이름표>", "launch": { ... } }]`를 넣는다. 이름표는 20자 이하(예: 배포판, 로컬판, 공개 모드). 로컬 웹 실행은 카드에 하나만.
- 이미 등록된 카드에 실행을 하나 더하려면 apps.json의 그 카드에서 기존 `launchLabel`·`moreLaunches`를 읽어 새 실행을 덧붙인 전체 목록으로 보낸다. `moreLaunches`를 빼고 보내면 기존 추가 실행은 그대로 남는다.
- 정말로 다른 앱(한 저장소 안의 별개 앱)일 때만 사용자에게 확인하고 `--new`로 새 카드를 만든다(dry-run과 등록 둘 다).

```bash
cat > /tmp/launcher-app.json <<'JSON'
{ ...확정한 초안... }
JSON
node <런처>/scripts/register.mjs /tmp/launcher-app.json --dry-run
```

## 5. 등록

```bash
node <런처>/scripts/register.mjs /tmp/launcher-app.json --capture
```

- `--capture`는 썸네일 파일이 없을 때 웹 주소·로컬 웹 앱의 화면을 자동으로 찍는다. 로컬 웹은 런처가 켜져 있어야 찍힌다.
- 출력의 `ok`가 false면 `error`를 그대로 보여 주고 초안을 고친다.
- `captureError`가 있으면 "썸네일은 기본 그림으로 두었어요. 런처 화면의 ✏ 수정에서 이미지를 넣을 수 있어요."라고 알린다.
- 런처 화면이 열려 있으면 카드가 저절로 나타난다.

## 6. 시험 실행 제안

"지금 런처에서 한 번 실행해 볼까요?" — 사용자가 원하면 런처 화면에서 카드를 눌러 달라고 안내한다(이 스킬은 실행 API를 직접 부르지 않는다).

## 하지 않는 것

- 배포 대행, 바탕화면 바로가기 자동 생성, 원본 프로젝트 파일 수정
