#!/usr/bin/env python3
# slot-kill: emergency stop for any in-flight live test.
# 1) cancels queued/in-progress slot-chain runs (kills the polling loop),
# 2) seals every open job's journal to step 8 (=> chain will NOT resume it),
# 3) removes .KILLTEST so the trigger is one-shot.
# Designed to run inside a GitHub Actions job (runner GH_TOKEN has actions:write
# + contents:write; the sandbox PAT has neither for actions).
import json, os, subprocess, sys, time, urllib.request, datetime as dt

TOK = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
REPO = os.environ.get("GITHUB_REPOSITORY") or "b9811507-del/live-test"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def api(path, method="GET"):
    req = urllib.request.Request(
        "https://api.github.com" + path, method=method,
        headers={"Authorization": "Bearer " + TOK,
                 "Accept": "application/vnd.github+json",
                 "Content-Length": "0"} if method == "GET" else
                {"Authorization": "Bearer " + TOK,
                 "Accept": "application/vnd.github+json",
                 "Content-Length": "0"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read()
        return json.loads(body) if body else {}
    except Exception as e:
        print("api err", path[:60], str(e)[:80])
        return None


def sh(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True)


def main():
    killed = []
    runs = api(f"/repos/{REPO}/actions/runs?status=in_progress,queued&per_page=50")
    for r in (runs or {}).get("workflow_runs") or []:
        if r.get("name") in ("slot-chain", "slot-guard") or \
           (r.get("path") or "").endswith(("slot-chain.yml", "slot-guard.yml")):
            if api(f"/repos/{REPO}/actions/runs/{r['id']}/cancel", "POST") is not None:
                killed.append(r["id"])
    print("cancelled runs:", killed or "none")

    # seal journals: any job mid-test (step 1..7) -> 8 = done (chain skips >=8)
    sp = os.path.join(ROOT, "state.json")
    st = {}
    if os.path.exists(sp):
        try:
            st = json.load(open(sp))
        except Exception:
            st = {}
    # engine keys days by IST date
    ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=330)
    dayk = ist.strftime("%Y-%m-%d")
    day = st.setdefault("days", {}).setdefault(dayk, {})
    sealed = []
    for job in ("malwa", "iari", "afo"):
        j = day.get(job)
        if isinstance(j, dict) and 0 < int(j.get("step", 0)) < 8:
            j["step"] = 8
            j["killed"] = True
            j["killed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            sealed.append(job)
        elif j is None:
            day[job] = {"step": 8, "killed": True, "note": "pre-empted by slot-kill"}
            sealed.append(job + "(pre)")
    if sealed:
        json.dump(st, open(sp, "w"), indent=0, sort_keys=True)
    print("sealed:", sealed or "nothing open")

    sh("git", "rm", "--quiet", "--ignore-unmatch", ".KILLTEST")
    sh("git", "add", "state.json")
    msg = "slot-kill: cancelled %s, sealed %s" % (killed or "[]", sealed or "[]")
    r = sh("git", "commit", "-q", "-m", msg)
    if r.returncode != 0:
        print("nothing to commit")
    else:
        sh("git", "fetch", "-q", "origin")
        sh("git", "rebase", "-q", "origin/main")
        pr = sh("git", "push", "-q",
                f"https://x-access-token:{TOK}@github.com/{REPO}.git",
                "HEAD:main")
        print("push:", "ok" if pr.returncode == 0 else pr.stderr.strip()[:120])
    print("DONE:", msg)


sys.exit(main())
