#!/usr/bin/env python3
# slot-kill v2: emergency stop for any in-flight live test.
#  1) cancel every queued/in-progress slot-chain & slot-guard run (kills the poll loop),
#  2) wait for them to die, re-pull state.json, then seal open jobs (0<step<8 -> 8),
#  3) remove .KILLTEST (one-shot trigger) and push. Runner GITHUB_TOKEN has
#     actions:write + contents:write; sandbox PAT has neither (that's why this runs in GHA).
import json, os, subprocess, sys, time, urllib.request, datetime as dt

TOK = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
REPO = os.environ.get("GITHUB_REPOSITORY") or "b9811507-del/live-test"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HDR = {"Authorization": "Bearer " + TOK, "Accept": "application/vnd.github+json"}


def api(path, method="GET"):
    req = urllib.request.Request("https://api.github.com" + path, method=method, headers=HDR)
    try:
        r = urllib.request.urlopen(req, timeout=25)
        body = r.read()
        return json.loads(body) if body else {}
    except Exception as e:
        print("api err", method, path[:70], str(e)[:90])
        return None


def sh(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True)


def main():
    # 1) cancel active chain runs (filter statuses client-side; API has no multi-status filter)
    killed = []
    runs = api(f"/repos/{REPO}/actions/runs?per_page=20")
    for r in (runs or {}).get("workflow_runs") or []:
        if r.get("status") in ("completed",):
            continue
        name = r.get("name") or ""
        if "slot-chain" in name or "slot-guard" in name:
            if api(f"/repos/{REPO}/actions/runs/{r['id']}/cancel", "POST") is not None:
                killed.append(r["id"])
    print("cancelled runs:", killed or "none")

    # 2) give cancelled runs a moment to actually die, then seal journals
    time.sleep(15)
    sh("git", "config", "user.email", "slot-kill@local")
    sh("git", "config", "user.name", "slot-kill")
    sh("git", "fetch", "-q", "origin")
    sh("git", "reset", "-q", "--hard", "origin/main")
    sp = os.path.join(ROOT, "state.json")
    try:
        st = json.load(open(sp))
    except Exception:
        st = {}
    ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=330)  # IST calendar day
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
    if sealed:
        json.dump(st, open(sp, "w"), indent=0, sort_keys=True)
        sh("git", "add", "state.json")
    print("sealed:", sealed or "nothing open")

    # 3) consume the trigger file (same commit; absence => commit still fine)
    sh("git", "rm", "-q", "--ignore-unmatch", ".KILLTEST")
    msg = "slot-kill: cancelled %s, sealed %s" % (killed or [], sealed or [])
    r = sh("git", "commit", "-q", "-m", msg)
    if r.returncode != 0:
        print("commit rc:", r.stdout.strip()[:80], r.stderr.strip()[:120])
    else:
        sh("git", "fetch", "-q", "origin")
        sh("git", "rebase", "-q", "origin/main")
        pr = sh("git", "push", "-q",
                f"https://x-access-token:{TOK}@github.com/{REPO}.git", "HEAD:main")
        print("push:", "ok" if pr.returncode == 0 else pr.stderr.strip()[:140])
    # 4) tell the admin (best-effort)
    adm = os.environ.get("ADMIN_CHAT") or ""
    token = os.environ.get("TG_TOKEN") or ""
    if adm and token:
        body = json.dumps({"chat_id": adm, "text": "🛑 slot-kill: runs " + str(killed) +
                           ", sealed " + str(sealed) + " (chain will skip sealed jobs)"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=15)
            print("admin notified")
        except Exception as e:
            print("notify err", str(e)[:60])
    print("DONE:", msg)


sys.exit(main())
