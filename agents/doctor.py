#!/usr/bin/env python3
"""agent-doctor — reads FAILED workflow runs of this repo, understands the error with LLM,
applies safe auto-fixes (transient → re-run; code bug in engine/renderapp → patch+push if it compiles),
and DMs SatyamSir what it did. Runs on schedule + manual dispatch. Silent when all is green."""
import os, sys, json, re, time, base64, tempfile, py_compile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from renderapp import llmsupport

TGT = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
GT = os.environ.get("GITHUB_TOKEN", "")
TG = os.environ.get("TG_TOKEN", "")
ADMIN = os.environ.get("ADMIN_CHAT", "1138783169")
SINCE = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 12 * 3600))
FIX_FILES_RE = re.compile(r"^(engine/|renderapp/)[\w./-]+\.py$")


def gh(method, path, body=None, accept="application/vnd.github+json"):
    rq = urllib.request.Request(f"https://api.github.com{path}",
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {GT}", "Accept": accept,
                 "Content-Type": "application/json", "User-Agent": "agent-doctor",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(rq, timeout=35) as r:
        d = r.read()
    return json.loads(d) if d else {}


def dm(text):
    if not TG or not text:
        print("(no DM)", text[:120]); return
    try:
        _post_tg(text)
    except Exception as e:
        print("dm fail:", e)


def _post_tg(text):
    rq = urllib.request.Request(f"https://api.telegram.org/bot{TG}/sendMessage",
        data=json.dumps({"chat_id": ADMIN, "text": text[:3900], "parse_mode": "HTML",
                         "disable_web_page_preview": True}).encode(),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(rq, timeout=20).read()


def failed_runs():
    d = gh("GET", f"/repos/{TGT}/actions/runs?status=failure&per_page=6&created=..{SINCE[1:-1]}")
    if "workflow_runs" not in d:
        d = gh("GET", f"/repos/{TGT}/actions/runs?status=failure&per_page=6")
    return [r for r in d.get("workflow_runs", [])
            if r.get("name") not in ("agent-doctor", "agent-sentinel")
            and r["created_at"] >= SINCE and not r.get("display_title", "").startswith("[agent-doctor]")]


def job_error(run_id):
    jobs = gh("GET", f"/repos/{TGT}/actions/runs/{run_id}/jobs").get("jobs", [])
    for j in jobs:
        for st in j.get("steps", []):
            if st.get("conclusion") == "failure":
                ann = gh("GET", f"{j['url']}/annotations")
                txt = "\n".join(a.get("blob_url", "") + " " + (a.get("message") or "")[:600] for a in ann if isinstance(ann, list))
                return j["name"], st.get("name"), txt[:2500] or (j.get("steps") and "no annotations") or ""
    return None, None, ""


TRANSIENT = re.compile(r"(curl.*(7|28)|timed?\s*out|connection (reset|refused)|429|rate.?limit|"
                       r"temporary failure|could not resolve|EOF occurred|network|Resource temporarily)", re.I)


def fixable(stepname, err):
    return bool(err) and not TRANSIENT.search(err)


def patch_file(path, fixed, why, run_id):
    rq = urllib.request.Request(f"https://api.github.com/repos/{TGT}/contents/{path}",
        headers={"Authorization": f"Bearer {GT}", "Accept": "application/vnd.github.raw+json", "User-Agent": "agent-doctor"})
    orig = urllib.request.urlopen(rq, timeout=30).read().decode()
    if fixed == orig or len(fixed) < 30 or len(fixed) > max(2 * len(orig), len(orig) + 5000):
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(fixed); tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        print("compiled fail:", e); return None
    sha = gh("GET", f"/repos/{TGT}/contents/{path}").get("sha")
    msg = f"[agent-doctor] auto-fix {path} (run {run_id})"
    body = {"message": msg, "content": base64.b64encode(fixed.encode()).decode(), "branch": "main"}
    if sha:
        body["sha"] = sha
    r = gh("PUT", f"/repos/{TGT}/contents/{path}", body)
    return r.get("commit", {}).get("sha")


LLM_SYS = ("You are a senior Python SRE for a Telegram live-test system (GitHub Actions + Flask/Render). "
           "You get a failing run's error excerpt and the full current file. Reply with ONLY: "
           "<<<REPLY>>> one-line plain-Hinglish explanation for the admin, then "
           "<<<FIX>>>, then the COMPLETE fixed file content (python only, no fences). "
           "Only if the bug is IN this file. If it is infra/transient/no-safe-fix, reply ONLY 'SKIP: <reason>'.")


def doctor():
    runs = failed_runs()
    if not runs:
        return 0
    acted = []
    budget = 2
    for r in runs:
        if budget <= 0:
            break
        rid = r["id"]
        jname, stname, err = job_error(rid)
        if not stname:
            continue
        title = r.get("name", "?")
        if not fixable(stname, err):
            gh("POST", f"/repos/{TGT}/actions/runs/{rid}/rerun-failed-jobs")
            acted.append(f"♻️ <b>{title}</b> ({stname}) transient error — re-run triggered.")
            budget -= 1
            continue
        fm = re.findall(r"[\"']((?:engine|renderapp)/[\w./-]+\.py)[\"']", err)
        m2 = re.findall(r"File \"[^\"]*?((?:engine|renderapp)/[\w./-]+\.py)\"", err)
        files = [f for f in dict.fromkeys(m2 + fm) if FIX_FILES_RE.match(f)][:1]
        if not files:
            acted.append(f"🤖 <b>{title}</b> — error code-side but file unclear → analysis DM (no auto-patch).")
            a = llmsupport.ask(LLM_SYS, f"ERROR:\n{err[:1800]}\n\nRUN: {title}/{jname}", 1500)
            acted[-1] += "\n<pre>" + _html_esc(((a or "").replace("<<<REPLY>>>", "") or err)[:500]) + "</pre>"
            budget -= 1
            continue
        fpath = files[0]
        rq = urllib.request.Request(f"https://raw.githubusercontent.com/{TGT}/main/{fpath}",
                                    headers={"User-Agent": "agent-doctor"})
        orig = urllib.request.urlopen(rq, timeout=30).read().decode()
        a = llmsupport.ask(LLM_SYS, f"FILE {fpath}:\n<<<BEGIN\n{orig[:14000]}\nEND>>>\n\nERROR:\n{err[:1800]}", 3500)
        if not a or a.strip().startswith("SKIP"):
            acted.append(f"⚠️ <b>{title}</b> — LLM: {_html_esc((a or 'no answer')[:160])}")
            budget -= 1
            continue
        mm = re.search(r"<<<FIX>>>\s*```[a-z]*\s*(.*?)```", a, re.S) or re.search(r"<<<FIX>>>\s*(.*)$", a, re.S)
        fixed = (mm.group(1) if mm else a).strip()
        if fixed.startswith("python\n"):
            fixed = fixed[7:]
        why = a.split("<<<FIX>>>")[0].replace("<<<REPLY>>>", "").strip()[:200]
        sha = patch_file(fpath, fixed, why, rid)
        if sha:
            gh("POST", f"/repos/{TGT}/actions/runs/{rid}/rerun-failed-jobs")
            acted.append(f"🩹 <b>{title}</b> → <code>{fpath}</code> patched & pushed "
                         f"[{sha[:7]}], run re-triggered.\n<i>{_html_esc(why)}</i>")
            dm(f"✅ Pushed fix — bot services will pick it up on next deploy/redeploy if needed.")
        else:
            acted.append(f"🚫 <b>{title}</b> — fix rejected (compile/safety guard). Suggested: <pre>{_html_esc(why)}</pre>")
        budget -= 1
    if acted:
        dm("🤖 <b>agent-doctor report</b>\n" + "\n".join(acted))
    return len(acted)


def _html_esc(s):
    import html
    return html.escape(s or "")


if __name__ == "__main__":
    try:
        n = doctor()
        print("doctor done, actions:", n)
    except Exception as e:
        import traceback
        traceback.print_exc()
        dm(f"🤖 doctor itself failed: <code>{_html_esc(str(e))[:200]}</code>")
        sys.exit(1)
