#!/usr/bin/env python3
"""agents/kill.py — EMERGENCY STOP (SPEC v11 §7 / slot-kill.yml).

1. cancel every queued/in-progress slot-chain + slot-guard run (client-side filter: the API rejects
   comma-separated status values)
2. 15s grace so cancellations land
3. git reset --hard origin/main
4. seal every open job: step=8 + killed=true (+ done_at) — a sealed slot can never fire again
5. remove .KILLTEST if present
6. commit + push (retry with rebase) and DM the admin

Never deletes group messages or files. Runner must set git user.email/user.name.
"""
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
TOK = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
API = "https://api.github.com/repos/" + REPO
TARGETS = ("slot-chain.yml", "slot-guard.yml")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
DRY = os.environ.get("KILL_DRY", "") == "1"
HDR = {"Authorization": "Bearer " + TOK, "Accept": "application/vnd.github+json",
       "User-Agent": "agri-quiz-v11-kill", "Content-Type": "application/json"}


def log(*a):
    print("[kill]", *a, flush=True)


def api(method, path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=HDR)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else {}


def runs_by_status(status):
    out = []
    try:
        d = api("GET", "/actions/runs?status=%s&per_page=100" % status)
        out = d.get("workflow_runs") or []
    except Exception as e:
        log("runs query failed (%s): %s" % (status, str(e)[:80]))
    return out


def cancel_chain_runs():
    killed = []
    seen = set()
    for status in ("in_progress", "queued", "waiting", "pending", "requested"):
        for r in runs_by_status(status):
            p = (r.get("path") or "")
            name = (r.get("name") or "")
            if not any(t in p for t in TARGETS) and not any(t.split(".")[0] == name for t in TARGETS):
                continue
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            try:
                api("POST", "/actions/runs/%s/cancel" % r["id"], {})
                killed.append({"id": r["id"], "name": name, "status": status, "created": r.get("created_at")})
                log("cancelled run %s (%s, was %s)" % (r["id"], name, status))
            except Exception as e:
                log("cancel %s failed: %s" % (r["id"], str(e)[:80]))
    return killed


def sh(cmd, check=False):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if p.stdout.strip():
        log(p.stdout.strip()[:400])
    if p.stderr.strip():
        log("stderr:", p.stderr.strip()[:300])
    if check and p.returncode != 0:
        raise RuntimeError("cmd failed: %s" % cmd)
    return p.returncode


def main():
    killed = cancel_chain_runs()
    log("waiting 15s grace for cancellations to land")
    time.sleep(15)

    # --- repo side: reset to origin/main, seal open jobs
    sh("git config user.email 'quizbot@users.noreply.github.com'")
    sh("git config user.name 'agri-quiz-kill'")
    sh("git fetch origin main --quiet")
    if not DRY:
        sh("git reset --hard origin/main", check=True)
    sealed = []
    try:
        st = json.load(open("state.json", encoding="utf-8"))
    except Exception:
        st = {"days": {}}
    now = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    for day, jobs in (st.get("days") or {}).items():
        for job, j in (jobs or {}).items():
            if not isinstance(j, dict):
                continue
            if 0 < int(j.get("step", 0)) < 8:
                j["step"] = 8
                j["killed"] = True
                j["done_at"] = j.get("done_at") or now
                j["locked_by"] = ""
                sealed.append("%s/%s" % (day, job))
    st["killed_at"] = now
    st["killed_runs"] = killed
    st["kill_stamp"] = {"at": now, "runs": [k["id"] for k in killed], "sealed": sealed}
    for k in ("afo18",):
        if isinstance(st.get(k), dict) and 0 < int(st[k].get("step", 0)) < 8:
            st[k]["step"] = 8
            st[k]["killed"] = True
            st[k]["done_at"] = st[k].get("done_at") or now
    json.dump(st, open("state.json", "w", encoding="utf-8"), indent=0, sort_keys=True)
    log("sealed jobs:", sealed or "none")
    if os.path.exists(".KILLTEST"):
        os.remove(".KILLTEST")
        log("removed .KILLTEST")
    if not DRY:
        sh("git add -A state.json .KILLTEST")
        rc = sh("git commit -m 'EMERGENCY STOP: sealed step8+killed, %d run(s) cancelled' || true"
                % len(killed))
        if sh("git push origin HEAD:main --quiet") != 0:
            log("push rejected -> rebase retry")
            sh("git pull --rebase origin main || true")
            sh("git push origin HEAD:main --quiet")
    else:
        log("DRY run: repo untouched")

    # --- admin DM (rate limited is not needed for an emergency stop)
    admin = os.environ.get("ADMIN_CHAT", "").strip()
    tok = os.environ.get("EXAM_TG_TOKEN", "").strip()
    if admin and tok and not DRY:
        msg = ("🧯 EMERGENCY STOP — slot-kill chalaya gaya.\n"
               "• Cancelled runs: %d\n• Sealed jobs: %s\n• state.json sealed step8+killed\n"
               "Chain ab ruki hui hai. Dobara start karne ke liye slot-chain dispatch karo."
               % (len(killed), ", ".join(sealed) or "none"))
        try:
            req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % tok,
                                         data=json.dumps({"chat_id": admin, "text": msg}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=20)
            log("admin DM sent")
        except Exception as e:
            log("admin DM failed:", str(e)[:100])
    log("DONE killed=%d sealed=%s" % (len(killed), sealed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
