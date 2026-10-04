"""Self-test for collect_feedback.py. Run: python test_collect_feedback.py"""
import datetime as dt
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("collect_feedback", HERE / "collect_feedback.py")
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)

REMARK = "테스트에서 상수 값을 그대로 다시 확인하지 말고 공개 함수 동작을 검사해 줘"


def event(text, meta=False, uuid=None, ts=None, origin=None, **extra):
    ev = {"type": "user", "isMeta": meta, "message": {"role": "user", "content": text}, **extra}
    if ts:
        ev["timestamp"] = ts
    if uuid:
        ev["uuid"] = uuid
    if origin:
        ev["origin"] = {"kind": origin}
    return json.dumps(ev, ensure_ascii=False)


def blocks(*texts, origin=None):
    ev = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": t} for t in texts]}}
    if origin:
        ev["origin"] = {"kind": origin}
    return json.dumps(ev, ensure_ascii=False)


def tool_result():
    return json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "test 테스트 결과 출력 길게"}]}})


def collect(path):
    r = subprocess.run([sys.executable, str(HERE / "collect_feedback.py"), "--transcripts", str(path), "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else r.stderr)


def brute_groups(remarks):
    """Reference answer: all pairs compared, connected components."""
    n = len(remarks)
    sets = [cf.words(r["text"]) for r in remarks]
    parent = list(range(n))

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            a, b = sets[i], sets[j]
            if a and b and len(a & b) / len(a | b) >= cf.SIMILAR:
                parent[root(i)] = root(j)
    comps = {}
    for i in range(n):
        comps.setdefault(root(i), set()).add(i)
    return sorted(sorted(c) for c in comps.values() if len(c) >= 2)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    failed = []
    with tempfile.TemporaryDirectory() as d:
        Path(d, "s1.jsonl").write_text("\n".join([
            event(REMARK),
            event("좋아요"),
            event("<system-reminder>테스트 상수 값 공개 함수 동작</system-reminder>"),
            tool_result(),
            "not json",
            event("This session is being continued from a previous conversation 테스트 상수 값 공개 함수 동작 검사",
                  isCompactSummary=True),
        ]), encoding="utf-8")
        Path(d, "s2.jsonl").write_text("\n".join([
            event("또 테스트에서 상수 값을 그대로 확인했네, 공개 함수 동작을 검사해 줘"),
            event("README 제목 오타 하나 고쳐 줘", uuid="u-readme"),
            event("[Request interrupted by user]"),
            event("아주 오래전에 한 번 했던 테스트 상수 공개 함수 동작 검사 이야기", ts="2001-01-01T00:00:00Z"),
            event('<scheduled-task name="resume"> 테스트 상수 값 공개 함수 동작을 검사해 줘 </scheduled-task>'),
            # Said twice in one session: reported apart from cross-session repeats.
            event("보고는 항상 한국어로 짧게 써 줘 부탁해"),
            event("보고는 항상 한국어로 짧게 써 줘 제발"),
        ]), encoding="utf-8")
        # A resumed session repeats an earlier message with the same uuid: a copy, not a repeat.
        Path(d, "s2-resumed.jsonl").write_text(event("README 제목 오타 하나 고쳐 줘", uuid="u-readme"), encoding="utf-8")
        Path(d, "s3.jsonl").write_text(event(REMARK, meta=True), encoding="utf-8")
        Path(d, "s4.jsonl").write_text("\n".join([
            # origin decides: a task notification is not the human even without a tag.
            event("작업 알림 보고서 세 줄 요약 내용", origin="task-notification"),
            # The human's own text may start with a tag; it is kept.
            event("<b>이 문구</b> 굵게 하지 말고 그냥 일반 글씨로 써 줘", origin="human"),
            # An injected reminder block rides along with the human block; only the human block stays.
            blocks("<system-reminder>\nThe user opened file secret.txt\n</system-reminder>",
                   "커밋 메시지는 영어로 한 줄 요약부터 써 줘", origin="human"),
            event("[Request interrupted by user] 아니 그게 아니라 README 먼저 고쳐 달라고", origin="human"),
            # Without origin, blocks are judged one by one: the tagged block goes, the plain one stays.
            blocks("<ide_opened_file>x.py</ide_opened_file>", "함수 이름은 동사로 시작하게 바꿔 줘"),
        ]), encoding="utf-8")

        code, rep = collect(d)
        if code != 0:
            failed.append(f"exit {code}: {rep}")
        else:
            texts = [x["text"] for x in rep["remarks"]]
            if rep["scanned"]["sessions"] != 5:
                failed.append(f"expected 5 sessions scanned, got {rep['scanned']}")
            want = {REMARK, "또 테스트에서 상수 값을 그대로 확인했네, 공개 함수 동작을 검사해 줘", "README 제목 오타 하나 고쳐 줘",
                    "보고는 항상 한국어로 짧게 써 줘 부탁해", "보고는 항상 한국어로 짧게 써 줘 제발",
                    "<b>이 문구</b> 굵게 하지 말고 그냥 일반 글씨로 써 줘", "커밋 메시지는 영어로 한 줄 요약부터 써 줘",
                    "아니 그게 아니라 README 먼저 고쳐 달라고", "함수 이름은 동사로 시작하게 바꿔 줘"}
            if set(texts) != want or len(texts) != len(want):
                failed.append(f"remarks differ.\n  extra: {sorted(set(texts) - want)}\n  missing: {sorted(want - set(texts))}"
                              f"\n  count: {len(texts)}")
            if len(rep["repeats"]) != 1 or rep["repeats"][0]["sources"] != ["s1.jsonl", "s2.jsonl"]:
                failed.append(f"expected the one cross-session test remark, got {rep['repeats']}")
            within = rep["repeats_within_source"]
            if len(within) != 1 or within[0]["sources"] != ["s2.jsonl"] or within[0]["count"] != 2:
                failed.append(f"expected one repeat inside s2.jsonl, got {within}")

        # A single transcript file is a valid source.
        code, rep = collect(Path(d, "s4.jsonl"))
        if code != 0 or rep["scanned"]["sessions"] != 1 or len(rep["remarks"]) != 4:
            failed.append(f"single file source: {code} {rep if code else rep['remarks']}")

        code, err = collect(Path(d, "missing.jsonl"))
        if code != 2:
            failed.append(f"missing transcript path should be exit 2, got {code}")

    # A ~ B ~ C chains into one group even though A and C are not alike.
    a = {"source": "a", "where": "a", "who": "h", "text": "alpha beta gamma delta epsilon zeta"}
    b = {"source": "b", "where": "b", "who": "h", "text": "gamma delta epsilon zeta eta theta"}
    c = {"source": "c", "where": "c", "who": "h", "text": "epsilon zeta eta theta iota kappa"}
    across, within = cf.find_repeats([a, b, c])
    if len(across) != 1 or across[0]["count"] != 3:
        failed.append(f"chained remarks should form one group of 3, got {across}")

    # The fast grouping must equal comparing every pair.
    rng = random.Random(7)
    vocab = [f"w{i}" for i in range(40)]
    sample = [{"source": f"s{i % 9}", "where": str(i), "who": "h",
               "text": " ".join(rng.sample(vocab, rng.randint(3, 9)))} for i in range(400)]
    fast = sorted(sorted(int(m["where"]) for m in g) for g in cf.find_groups(sample))
    if fast != brute_groups(sample):
        failed.append("find_groups differs from the all-pairs reference")

    # 3000 remarks must group in seconds, not minutes.
    big_vocab = [f"word{i}" for i in range(400)] + ["the", "and", "to", "of"]
    big = [{"source": f"s{i % 20}", "where": str(i), "who": "h",
            "text": " ".join(rng.sample(big_vocab, 12) + ["the", "and"])} for i in range(3000)]
    t0 = time.perf_counter()
    cf.find_repeats(big)
    took = time.perf_counter() - t0
    if took > 5:
        failed.append(f"3000 remarks took {took:.1f}s")

    # GitHub reader with a fake gh: bots and excluded authors are dropped, the limit warns.
    def fake_gh(args):
        if args[:2] == ["pr", "list"]:
            return [{"number": n, "title": f"t{n}", "url": f"u{n}"} for n in range(1, cf.GH_LIMIT + 1)]
        if args[:2] == ["pr", "view"]:
            return {"comments": [{"author": {"login": "alice"}, "body": "please test through the public function"},
                                 {"author": {"login": "dependabot[bot]"}, "body": "bumps the version of some package"},
                                 {"author": {"login": "app", "is_bot": True}, "body": "coverage report changed by two"}],
                    "reviews": [{"author": {"login": "ci-helper"}, "body": "automated lint summary with findings"},
                                {"author": {"login": "bob"}, "body": "LGTM"}]}
        return [{"user": {"login": "github-actions", "type": "Bot"}, "body": "workflow run summary for this line"},
                {"user": {"login": "carol"}, "body": "name this function after what it returns"}]

    cf.WARNINGS.clear()
    got = cf.from_github("o/r", dt.date.today(), excluded={"ci-helper"}, gh=fake_gh)
    who = {r["who"] for r in got}
    if who != {"alice", "carol"} or len(got) != 2 * cf.GH_LIMIT:
        failed.append(f"github authors: {sorted(who)} count {len(got)}")
    if not cf.WARNINGS:
        failed.append("hitting the PR limit should warn")
    cf.WARNINGS.clear()
    if cf.from_github("o/r", dt.date.today(), gh=lambda args: None) != []:
        failed.append("gh returning null should read as no PRs")

    # No gh on PATH is an input error, not a crash or an empty report.
    with tempfile.TemporaryDirectory() as empty:
        r = subprocess.run([sys.executable, str(HERE / "collect_feedback.py"), "--gh-repo", "o/r"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PATH": empty})
        if r.returncode != 2 or "gh" not in r.stderr:
            failed.append(f"missing gh should be exit 2, got {r.returncode} {r.stderr}")

    r = subprocess.run([sys.executable, str(HERE / "collect_feedback.py")], capture_output=True, text=True)
    if r.returncode != 2:
        failed.append(f"no source should be a usage error, got exit {r.returncode}")

    # Several project folders: a lesson repeated across projects is "shared", one repeated inside a project is not.
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d, "proj-a"), Path(d, "proj-b")
        a.mkdir()
        b.mkdir()
        SHARED = "주석에는 날짜를 쓰지 말고 이유만 적어 줘 제발"
        LOCAL = "이 게임 시험은 화면 창구로 동작을 확인해 줘 다시"
        Path(a, "s1.jsonl").write_text("\n".join([event(SHARED, uuid="a1"), event(LOCAL, uuid="a2")]), encoding="utf-8")
        Path(a, "s2.jsonl").write_text(event(LOCAL + " 꼭", uuid="a3"), encoding="utf-8")
        Path(b, "s3.jsonl").write_text(event(SHARED + " 부탁해", uuid="b1"), encoding="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "collect_feedback.py"), "--transcripts", str(a), str(b), "--json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            failed.append(f"two folders: exit {r.returncode} {r.stderr}")
        else:
            rep = json.loads(r.stdout)
            scopes = {g["members"][0]["text"][:6]: (g["scope"], g["projects"]) for g in rep["repeats"]}
            if scopes.get(SHARED[:6]) != ("shared", ["proj-a", "proj-b"]):
                failed.append(f"cross-project repeat should be shared: {scopes}")
            if scopes.get(LOCAL[:6]) != ("project", ["proj-a"]):
                failed.append(f"one-project repeat should be project-scoped: {scopes}")
            if rep["scanned"]["sessions"] != 3:
                failed.append(f"two folders should scan 3 sessions, got {rep['scanned']}")
        wt = Path(d, "proj-a--claude-worktrees-brave-x1")
        wt.mkdir()
        Path(wt, "s4.jsonl").write_text(event(LOCAL + " 정말", uuid="w1"), encoding="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "collect_feedback.py"), "--transcripts", str(a), str(wt), "--json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        groups = json.loads(r.stdout)["repeats"] if r.returncode == 0 else []
        if not groups or any(g["scope"] != "project" or g["projects"] != ["proj-a"] for g in groups):
            failed.append(f"a worktree folder is the same project, not a second one: {[(g['scope'], g['projects']) for g in groups]}")
        r = subprocess.run([sys.executable, str(HERE / "collect_feedback.py"), "--transcripts", str(a), str(Path(d, "nope"))],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 2 or "nope" not in r.stderr:
            failed.append(f"a missing folder among several should be exit 2 naming it, got {r.returncode} {r.stderr}")

    for f in failed:
        print("FAIL", f)
    print("ok" if not failed else f"{len(failed)} failed")
    sys.exit(1 if failed else 0)
