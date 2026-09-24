"""Grade skill-eval runs.

Usage:
    python grade.py <eval-name> <job-dir> [<transcript.jsonl>]

Prints a JSON object {"expectations": [{"text", "passed", "evidence"}]} — the
grading.json shape skill-creator's viewer expects. Checks marked "judge" in
evals.json are not graded here; a separate judge model grades those.
"""
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent / ".claude" / "skills"
SERVER_MD5 = hashlib.md5(
    (SKILLS / "non-ascii-via-file/evals/fixtures/notes-api/server.py").read_bytes()
).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def tool_calls(transcript):
    """Yield (tool_name, input_dict) in order from a subagent JSONL transcript."""
    if not transcript:
        return []
    calls = []
    for line in Path(transcript).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append((block.get("name"), block.get("input") or {}))
    return calls


def shell_commands(calls):
    return [i.get("command", "") for n, i in calls if n in ("Bash", "PowerShell")]


def exp(text, passed, evidence):
    return {"text": text, "passed": bool(passed), "evidence": evidence}


def run_tests(job, test_file):
    r = subprocess.run([sys.executable, test_file], cwd=job, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout + r.stderr).strip()[-200:]


def notes(job):
    p = job / "notes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


HANGUL = re.compile(r"[가-힣]")


def curl_checks(calls):
    cmds = [c for c in shell_commands(calls) if "curl" in c]
    inline = [c for c in cmds if re.search(r"(-d|--data(-raw|-binary)?)\s+['\"][^@]", c) and HANGUL.search(c)]
    via_file = [c for c in cmds if re.search(r"(-d|--data(-binary|-raw)?)\s+['\"]?@", c)]
    return cmds, inline, via_file


def g_curl_create(job, calls):
    ns = notes(job)
    ok = any(n["title"] == "필라테스 예약 변경" and n["body"] == "화요일 7시 → 목요일 8시로 옮김" for n in ns)
    cmds, inline, via_file = curl_checks(calls)
    return [
        exp("notes.json 에 제목·본문이 정확히 저장됨", ok, json.dumps(ns, ensure_ascii=False)[:200]),
        exp("한글을 curl 인자로 직접 넣은 호출 없음", calls and not inline, f"inline={len(inline)} of {len(cmds)} curl calls"),
        exp("curl 이 @file 로 본문을 읽음", via_file, via_file[0][:150] if via_file else "none"),
    ]


def g_misdiagnosis(job, calls):
    md5 = hashlib.md5((job / "server.py").read_bytes()).hexdigest()
    ns = notes(job)
    ok = any(n["title"] == "회의록" and n["body"] == "3분기 목표 정리" for n in ns)
    return [
        exp("server.py 가 원본과 동일(멀쩡한 서버를 고치지 않음)", md5 == SERVER_MD5, f"md5={md5}"),
        exp("notes.json 에 title='회의록', body='3분기 목표 정리' 저장됨", ok, json.dumps(ns, ensure_ascii=False)[:200]),
    ]


def g_phone(job, calls):
    f = load_module(job / "phone.py", "phone_eval").format_phone
    cases = {
        "seoul": [("02-123-4567", "02-123-4567"), ("0212345678", "02-1234-5678"), ("(02) 3456-7890", "02-3456-7890")],
        "rep": [("1588-1234", "1588-1234"), ("15771234", "1577-1234")],
    }
    out = []
    for key, label in (("seoul", "02 지역번호 정답"), ("rep", "15xx 대표번호 정답")):
        got = []
        for raw, want in cases[key]:
            try:
                v = f(raw)
            except Exception as e:  # noqa: BLE001 — record any failure as evidence
                v = f"<{type(e).__name__}>"
            got.append((raw, v, want))
        out.append(exp(label, all(v == w for _, v, w in got), "; ".join(f"{r}->{v}" for r, v, _ in got)))
    passed, log = run_tests(job, "test_phone.py")
    out.append(exp("기존 test_phone.py 통과", passed, log))
    clean = job / "customers_clean.csv"
    rows = list(csv.DictReader(clean.open(encoding="utf-8-sig"))) if clean.exists() else []
    out.append(exp("customers_clean.csv 에 phone_clean 컬럼 존재", rows and "phone_clean" in rows[0], f"rows={len(rows)}"))
    return out


def g_splitter(job, calls):
    s = load_module(job / "splitter.py", "splitter_eval").split_sentences
    text = (job / "sample_news.txt").read_text(encoding="utf-8")
    parts = s(text)
    broken = [p for p in parts if re.match(r"^\d", p) and not re.match(r"^\d+\.\s", p)]
    whole = all(any(tok in p for p in parts) for tok in ("3.5%", "1,385.2원", "1.2조"))
    empties = [p for p in parts if re.fullmatch(r"[.\s]+", p)]
    passed, log = run_tests(job, "test_splitter.py")
    ran = [c for c in shell_commands(calls) if "sample_news" in c or "split_sentences" in c]
    return [
        exp("소수점(3.5%, 1,385.2원, 1.2조)을 쪼개지 않음", whole and not broken, f"broken={broken[:3]}"),
        exp("'...' 이 빈 조각을 만들지 않음", not empties, f"empties={empties[:3]}"),
        exp("기존 test_splitter.py 통과", passed, log),
        exp("샘플 기사로 실제 실행한 기록 있음", ran, ran[0][:150] if ran else "none"),
    ]


def first_write_index(calls, pattern):
    for i, (n, inp) in enumerate(calls):
        if n in ("Write", "Edit") and re.search(pattern, inp.get("file_path", "").replace("\\", "/")):
            return i
    return None


def table_before_code(calls, code_file):
    code_i = first_write_index(calls, rf"/{code_file}$")
    table_i = None
    for i, (n, inp) in enumerate(calls):
        if n in ("Write", "Edit"):
            path = inp.get("file_path", "").replace("\\", "/")
            if path.endswith(f"/{code_file}"):
                continue
            if re.search(r"(table|answer|정답|case|test_)", path, re.I):
                table_i = i
                break
    ok = table_i is not None and code_i is not None and table_i < code_i
    return exp("정답표(또는 테스트 데이터)가 구현 코드보다 먼저 작성됨", ok, f"table_write_idx={table_i} code_write_idx={code_i}")


def g_ro(job, calls):
    f = load_module(job / "ro.py", "ro_eval").attach_ro
    hangul = {"서울": "서울로", "부산": "부산으로", "학교": "학교로", "집": "집으로", "물": "물로",
              "연필": "연필로", "강": "강으로", "바다": "바다로", "칼": "칼로", "밖": "밖으로"}
    digits = {"1": "1로", "3": "3으로", "7": "7로", "10": "10으로"}

    def score(table):
        got = {}
        for k, want in table.items():
            try:
                got[k] = f(k)
            except Exception as e:  # noqa: BLE001
                got[k] = f"<{type(e).__name__}>"
        good = sum(got[k] == w for k, w in table.items())
        return good, got

    hg, hgot = score(hangul)
    dg, dgot = score(digits)
    wrong_digits = {k: v for k, v in dgot.items() if v != digits[k] and not v.startswith("<")}
    return [
        exp("보류 세트 한글 10개 전부 정답", hg == len(hangul), f"{hg}/{len(hangul)} wrong={ {k: v for k, v in hgot.items() if v != hangul[k]} }"),
        exp("숫자 끝 단어 정답 또는 명시적 예외(오답 없음)", not wrong_digits, f"{dg}/{len(digits)} got={dgot}"),
        table_before_code(calls, "ro.py"),
    ]


def g_plural(job, calls):
    f = load_module(job / "plural.py", "plural_eval").pluralize
    regular = {"city": "cities", "day": "days", "bus": "buses", "box": "boxes", "piano": "pianos"}
    irregular = {"child": "children", "sheep": "sheep", "mouse": "mice", "person": "people",
                 "analysis": "analyses", "knife": "knives", "leaf": "leaves", "roof": "roofs",
                 "chief": "chiefs", "hero": "heroes", "photo": "photos"}

    def score(table):
        got = {k: f(k) for k in table}
        return sum(got[k] == w for k, w in table.items()), {k: v for k, v in got.items() if v != table[k]}

    rg, rwrong = score(regular)
    ig, iwrong = score(irregular)
    return [
        exp("규칙형 5개 전부 정답", rg == len(regular), f"{rg}/5 wrong={rwrong}"),
        exp("불규칙·예외 11개 전부 정답", ig == len(irregular), f"{ig}/11 wrong={iwrong}"),
        table_before_code(calls, "plural.py"),
    ]


GRADERS = {
    "curl-create-korean-note": g_curl_create,
    "misdiagnosed-parse-error": g_misdiagnosis,
    "phone-normalizer-real-csv": g_phone,
    "sentence-splitter-real-news": g_splitter,
    "korean-particle-euro-ro": g_ro,
    "english-pluralize": g_plural,
}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    name, job = sys.argv[1], Path(sys.argv[2])
    calls = tool_calls(sys.argv[3] if len(sys.argv) > 3 else None)
    try:
        result = GRADERS[name](job, calls)
    except Exception as e:  # noqa: BLE001 — a crashing deliverable is a failed run, not a grader crash
        result = [exp("산출물 로드/실행", False, f"{type(e).__name__}: {e}")]
    print(json.dumps({"expectations": result}, ensure_ascii=False, indent=2))
