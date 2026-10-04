"""Self-test for check_pr_body.py. Run: python test_check_pr_body.py"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_pr_body", HERE / "check_pr_body.py")
cpb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpb)

GOOD = """## Summary
```
cli add <name> --tag   # new flag
```

## Evidence
- `pytest -q` -> 42 passed

## Merge Danger
**Door:** two-way
**Blast radius:** localized
"""

KOREAN = """## 요약
- 새 명령 하나

## 증거
- 실행 결과 3건 통과

## 머지 위험
- 문: 단방향 (메일이 실제로 나감)
- 영향 범위: users
"""

TAIL = "\n## Evidence\n- pytest -> 3 passed\n\n## Merge Danger\nDoor: two-way\nBlast radius: localized\n"
MAIL = "+++ b/app/mailer.py\n+    send_mail(all_users, subject)\n"


def cli(args, body=None, body_bytes=None, diff_bytes=None, env=None, std=""):
    # The developer's own user-level standards file must not change these results; std=None keeps env as given.
    env = dict(os.environ if env is None else env)
    if std is not None:
        env["REVIEW_STANDARDS"] = std
    with tempfile.TemporaryDirectory() as d:
        argv = [sys.executable, str(HERE / "check_pr_body.py"), "--json"]
        if body is not None or body_bytes is not None:
            b = Path(d) / "body.md"
            b.write_bytes(body_bytes if body_bytes is not None else body.encode("utf-8"))
            argv.append(str(b))
        if diff_bytes is not None:
            p = Path(d) / "c.diff"
            p.write_bytes(diff_bytes)
            argv += ["--diff", str(p)]
        r = subprocess.run(argv + args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        return r.returncode, r.stdout, r.stderr


def skill_template():
    text = (HERE.parent / "SKILL.md").read_text(encoding="utf-8")
    return re.search(r"```markdown\n(.*?)\n```", text, re.S).group(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    failed = []

    def expect(name, ok, **want):
        def run(body, diff=None):
            rep = cpb.check(body, diff)
            bad = rep["ok"] != ok or any(rep.get(k) != v for k, v in want.items())
            if bad:
                failed.append(f"{name}: {rep}")
            return rep
        return run

    # Complete bodies.
    expect("complete body", True, door="two-way", review="light", blast_radius="localized")(GOOD)
    expect("korean headings", True, door="one-way", review="full")(KOREAN)
    expect("h3 headings with colons", True, door="two-way")(
        "### Summary:\nx\n### Evidence:\n- 1 passed\n### Merge Danger:\n**Door:** two-way\n**Blast radius:** localized\n")

    # Missing or empty parts.
    rep = expect("missing merge danger", False)(GOOD.split("## Merge Danger")[0])
    if not any("Merge Danger" in p for p in rep["problems"]):
        failed.append(f"missing merge danger not named: {rep['problems']}")
    expect("TODO evidence", False)(GOOD.replace("- `pytest -q` -> 42 passed", "TODO"))
    expect("all-placeholder evidence lines", False)(GOOD.replace("- `pytest -q` -> 42 passed", "- TODO\n- TBD\n- <결과>"))
    expect("unknown door", False)(GOOD.replace("**Door:** two-way", "**Door:** maybe"))
    expect("placeholder radius", False)(GOOD.replace("**Blast radius:** localized", "**Blast radius:** TBD"))
    expect("empty bold radius", False, blast_radius=None)(GOOD.replace("**Blast radius:** localized", "**Blast radius:**"))

    # The template in SKILL.md, sent as is, must not pass.
    rep = expect("SKILL template as is", False, door=None)(skill_template())
    joined = " ".join(rep["problems"])
    for part in ("Summary", "Evidence", "template slot", "Blast radius"):
        if part not in joined:
            failed.append(f"SKILL template: no problem mentions {part!r}: {rep['problems']}")
    expect("comment-only sections", False)("## Summary\n<!-- 가장 작은 그림 -->\n## Evidence\n<!-- 결과\n여러 줄 -->\n"
                                           "## Merge Danger\nDoor: two-way\nBlast radius: localized\n")

    expect("multi-line comment as evidence", False)("## Summary\n- one flag added\n## Evidence\n<!--\n실제로 돌려 본 결과.\n-->\n"
                                                   "## Merge Danger\nDoor: two-way\nBlast radius: localized\n")

    # Sub-headings stay inside their section; same-or-higher headings close it.
    expect("call-tree sub-heading", True)("## Summary\n### Call tree\n```\nmain -> run\n```\n" + TAIL)
    expect("door sub-headings", True, door="two-way", blast_radius="localized")(
        "## Summary\nx\n## Evidence\ny\n## Merge Danger\n### Door\ntwo-way\n### Blast radius\nlocalized\n")
    expect("unrelated h2 closes section", False)("## Summary\n## Notes\nlots of text\n" + TAIL)

    # Code fences hide headings and fields.
    expect("fenced fake sections", False, door=None)("## Summary\n```\n## Evidence\nok\n## Merge Danger\nDoor: two-way\n"
                                                     "Blast radius: x\n```\n")
    expect("tilde fence", False)("## Summary\n~~~\n## Evidence\n~~~\n## Merge Danger\nDoor: two-way\nBlast radius: x\n")
    expect("python comment in fence", True)("## Summary\n```python\n# step 1: parse\nparse()\n```\n" + TAIL)

    # Evidence title: "확인" alone, not "확인 못 한 것".
    expect("확인 heading", True)("## 요약\nx\n## 확인:\n- 3 passed\n## 머지 위험\n문: 양방향\n영향 범위: module\n")
    expect("확인 못 한 것 is not evidence", False)("## Summary\nx\n## 확인 못 한 것\n- 화면 검사(시간 부족)\n## Merge Danger\n"
                                                 "Door: two-way\nBlast radius: localized\n")

    # Door values.
    for raw in ("`two-way`", "**two-way**", "two way", "Two-way door", "two_way"):
        expect(f"door {raw!r}", True, door="two-way")(GOOD.replace("**Door:** two-way", f"**Door:** {raw}"))
    for raw in ("not one-way, it's two-way", "one-way? no — two-way", "<one-way | two-way>"):
        expect(f"door {raw!r}", False, door=None)(GOOD.replace("**Door:** two-way", f"**Door:** {raw}"))
    expect("reason in parentheses may name the other door", True, door="two-way")(
        GOOD.replace("**Door:** two-way", "**Door:** two-way (not one-way: dry-run sink)"))

    # Reasons next to one-way signals.
    expect("two-way next to mail, no reason", False)(GOOD, MAIL)
    rep = expect("two-way next to mail, reason in parentheses", True)(
        GOOD.replace("**Door:** two-way", "**Door:** two-way (mail goes to a dry-run sink, revert restores it)"), MAIL)
    if not rep["warnings"]:
        failed.append("explained two-way should still warn")
    expect("two-way next to mail, Reason field", True)(GOOD.replace("**Blast radius:**", "**Reason:** sink only\n**Blast radius:**"), MAIL)
    expect("Reason field left as template slot", False)(GOOD.replace("**Blast radius:**", "**Reason:** <한 줄>\n**Blast radius:**"), MAIL)
    expect("free text with 'since' is not a reason", False)(GOOD.replace("**Blast radius:**", "Since nobody reviewed it.\n**Blast radius:**"), MAIL)
    expect("one-way next to mail needs no reason", True, review="full")(GOOD.replace("**Door:** two-way", "**Door:** one-way"), MAIL)

    # Signal scanning.
    def signals(diff):
        return cpb.scan_diff(diff)

    no_signal = {
        "README typo": "+++ b/README.md\n+typo fix\n",
        "context line": "diff --git a/app/db.py b/app/db.py\n@@ -10,3 +10,4 @@\n     cur.execute('DELETE FROM s')\n+    log.info('x')\n",
        "doc mentions push": "diff --git a/docs/deployment-notes.md b/docs/deployment-notes.md\n+we never git push from CI\n",
        "skill doc": "+++ b/.claude/skills/x/SKILL.md\n+  - 공개·배포: push, publish, git push\n",
        "deployer substring": "+++ b/src/deployer_utils/helpers.py\n+x=1\n",
        "email field": "+++ b/app/models.py\n+    email: str\n+    user.email = form.email\n",
        "env example": "+++ b/.env.example\n+API_KEY=\n",
        "removed sql comment in hunk": "diff --git a/q.sql b/q.sql\n@@ -1 +1 @@\n--- old note\n+-- new note\n",
    }
    for name, d in no_signal.items():
        if signals(d):
            failed.append(f"false signal for {name}: {signals(d)}")

    want = {
        "removed send_mail": ("diff --git a/m.py b/m.py\n-    send_mail(users)\n+    pass\n", "outbound message"),
        "smtplib": ("+++ b/a.py\n+import smtplib\n", "outbound message"),
        "nodemailer": ("+++ b/a.js\n+const nodemailer = require('nodemailer')\n", "outbound message"),
        "webhooks.send": ("+++ b/a.py\n+webhooks.send(evt)\n", "outbound message"),
        "db/migrate": ("+++ b/db/migrate/20240101_add.rb\n+x\n", "database migration"),
        "alembic": ("+++ b/alembic/versions/abc.py\n+x\n", "database migration"),
        "docker push": ("+++ b/Makefile\n+\tdocker push img\n", "publish or push"),
        "gh release": ("+++ b/release.sh\n+gh release create v1\n", "publish or push"),
        "terraform": ("+++ b/ci.sh\n+terraform apply -auto-approve\n", "deploy or infrastructure change"),
        "kubectl": ("+++ b/ci.sh\n+kubectl apply -f k8s/\n", "deploy or infrastructure change"),
        "drop index": ("+++ b/q.py\n+cur.execute('DROP INDEX idx')\n", "schema change or drop"),
        "rm -fr list": ("+++ b/a.py\n+subprocess.run(['rm', '-fr', path])\n", "file deletion"),
        "os.remove": ("+++ b/a.py\n+os.remove(p)\n", "file deletion"),
        ".env": ("+++ b/.env\n+API_KEY=x\n", "secrets or credentials"),
        ".env.production": ("diff --git a/.env.production b/.env.production\n", "secrets or credentials"),
        "openapi": ("+++ b/openapi.yaml\n-  /v1/users:\n", "public contract (API, schema, wire format)"),
        "proto": ("+++ b/api/user.proto\n+x\n", "public contract (API, schema, wire format)"),
        "schema": ("+++ b/db/schema.sql\n+x\n", "public contract (API, schema, wire format)"),
        "workflow": ("+++ b/.github/workflows/ci.yml\n+x\n", "deploy or CI pipeline"),
        "deploy dir": ("+++ b/deploy/prod.sh\n+x\n", "deploy or CI pipeline"),
        "second file of plain diff -u": ("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n+a\n--- a/migrations/1.py\n+++ b/migrations/1.py\n"
                                         "@@ -0,0 +1 @@\n+b\n", "database migration"),
    }
    for name, (d, label) in want.items():
        if label not in signals(d):
            failed.append(f"missed signal {label!r} for {name}: {signals(d)}")

    # CLI: encodings, input errors, exit codes.
    code, out, _ = cli([], body_bytes=b"\xef\xbb\xbf" + GOOD.encode("utf-8"))
    if code != 0:
        failed.append(f"UTF-8 BOM body rejected: {code} {out}")
    code, _, err = cli([], body=GOOD, diff_bytes=MAIL.encode("utf-16"))
    if code != 2 or "UTF-16" not in err:
        failed.append(f"UTF-16 diff must be exit 2, got {code} {err}")
    code, _, err = cli([], body=GOOD, diff_bytes=b"+++ b/a.py\n+x\x00y\n")
    if code != 2:
        failed.append(f"diff with NUL must be exit 2, got {code}")
    code, _, err = cli([], body_bytes=GOOD.encode("utf-16"))
    if code != 2:
        failed.append(f"UTF-16 body must be exit 2, got {code}")
    code, out, _ = cli([], body=GOOD, diff_bytes=MAIL.encode("utf-8"))
    if code != 1 or "outbound message" not in json.loads(out)["one_way_signals"]:
        failed.append(f"CLI diff scan: {code} {out}")
    code, _, err = cli([str(HERE / "no-such-body.md")])
    if code != 2:
        failed.append(f"missing body file must be exit 2, got {code} {err}")
    code, _, err = cli(["--gh", "1"], body=GOOD)
    if code != 2:
        failed.append(f"body file plus --gh must be exit 2, got {code}")
    code, _, _ = cli([])
    if code != 2:
        failed.append(f"no input must be exit 2, got {code}")
    with tempfile.TemporaryDirectory() as empty:
        env = {**os.environ, "PATH": empty}
        code, _, err = cli(["--gh", "1"], env=env)
        if code != 2 or "gh" not in err:
            failed.append(f"missing gh must be exit 2, got {code} {err}")

    # User-level one-way rules.
    STD = r"""# my standards

```one-way
# name | repo | where | regex | block
blog post | tigermorning.github.io | path | ^ko/[^/]+\.html$ |
leak | !private-* | content | (?i)secret-project | block
vendored asset | * | path | (^|/)vendor/
```
"""
    BLOG = "diff --git a/ko/new.html b/ko/new.html\n@@ -0,0 +1 @@\n+<h1>x</h1>\n"
    LEAK = "diff --git a/README.md b/README.md\n@@ -1 +1,2 @@\n+see secret-project notes\n"
    VENDOR = "diff --git a/vendor/three.js b/vendor/three.js\n@@ -0,0 +1 @@\n+x\n"
    with tempfile.TemporaryDirectory() as d:
        std = Path(d) / "review-standards.md"
        std.write_text(STD, encoding="utf-8")
        rules = cpb.load_user_signals(std)
        if [r["label"] for r in rules] != ["blog post", "leak", "vendored asset"] or not rules[1]["block"]:
            failed.append(f"user rules parsed wrong: {rules}")

        def user(name, diff, repo, ok, has=None, lacks=None, body=GOOD):
            rep = cpb.check(body, diff, rules, repo)
            if rep["ok"] != ok or (has and has not in rep["one_way_signals"]) or (lacks and lacks in rep["one_way_signals"]):
                failed.append(f"user rule {name}: {rep}")

        if any(r["pattern"].pattern.endswith("|") for r in rules):
            failed.append(f"trailing empty cell glued onto a regex: {[r['pattern'].pattern for r in rules]}")
        user("blog path in blog repo", BLOG, "tigermorning.github.io", False, has="yours: blog post")
        user("other path in blog repo", "diff --git a/README.md b/README.md\n@@ -1 +1 @@\n+x\n", "tigermorning.github.io",
             True, lacks="yours: blog post")
        user("non-vendor path", "diff --git a/src/app.py b/src/app.py\n@@ -1 +1 @@\n+x\n", None, True, lacks="yours: vendored asset")
        user("blog path elsewhere", BLOG, "my-skills", True, lacks="yours: blog post")
        user("blog rule with unknown repo", BLOG, None, True, lacks="yours: blog post")
        user("leak in a README blocks", LEAK, "my-skills", False, has="yours: leak",
             body=GOOD.replace("**Door:** two-way", "**Door:** one-way"))
        user("leak rule skips its own repos", LEAK, "private-notes", True, lacks="yours: leak")
        user("any-repo path rule", VENDOR, None, False, has="yours: vendored asset")
        user("explained two-way next to a user signal", VENDOR, "x", True, has="yours: vendored asset",
             body=GOOD.replace("**Door:** two-way", "**Door:** two-way (pinned copy, revert drops it)"))

        for glob, repo, want in (("*", None, True), ("!private-*", "private-a", False), ("!private-*", "blog", True),
                                 ("My-Skills", "my-skills", True), ("blog", None, False), ("!private-*", None, False),
                                 ("!private-*,!game-proto", "game-proto", False), ("!private-*,!game-proto", "blog", True),
                                 ("blog, notes", "notes", True), ("blog, notes", "other", False)):
            if cpb.repo_matches(glob, repo) != want:
                failed.append(f"repo_matches({glob!r}, {repo!r}) should be {want}")

        code, out, err = cli(["--repo", "tigermorning.github.io"], body=GOOD, diff_bytes=BLOG.encode(), std=str(std))
        rep = json.loads(out) if code in (0, 1) else {}
        if code != 1 or rep.get("user_standards") != str(std) or "yours: blog post" not in rep.get("one_way_signals", []):
            failed.append(f"REVIEW_STANDARDS env not used: {code} {out} {err}")
        code, out, _ = cli(["--repo", "tigermorning.github.io", "--no-user-standards"], body=GOOD,
                           diff_bytes=BLOG.encode(), std=str(std))
        if code != 0 or json.loads(out)["user_standards"] is not None:
            failed.append(f"--no-user-standards should skip the file: {code} {out}")
        code, _, err = cli(["--user-standards", str(Path(d) / "missing.md")], body=GOOD)
        if code != 2 or "not found" not in err:
            failed.append(f"named but missing standards file must be exit 2, got {code} {err}")
        bad = Path(d) / "bad.md"
        bad.write_text("```one-way\nx | * | content | (unclosed\n```\n", encoding="utf-8")
        code, _, err = cli(["--user-standards", str(bad)], body=GOOD)
        if code != 2 or "bad regex" not in err:
            failed.append(f"bad user regex must be exit 2, got {code} {err}")
        bad.write_text("```one-way\nall | * | path | (a|) |\n```\n", encoding="utf-8")
        code, _, err = cli(["--user-standards", str(bad)], body=GOOD)
        if code != 2 or "empty string" not in err:
            failed.append(f"a regex matching everything must be exit 2, got {code} {err}")
        bad.write_text("```one-way\nonly | two\n```\n", encoding="utf-8")
        code, _, err = cli(["--user-standards", str(bad)], body=GOOD)
        if code != 2:
            failed.append(f"malformed user rule must be exit 2, got {code} {err}")

    for f in failed:
        print("FAIL", f)
    print("ok" if not failed else f"{len(failed)} failed")
    sys.exit(1 if failed else 0)
