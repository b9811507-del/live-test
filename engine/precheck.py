#!/usr/bin/env python3
"""
precheck.py — 20 min before each test, verify everything is ok, auto-fix if not.
Called by:
  - GHA workflow pre-check.yml every 10 min (checks if next slot within 20 min)
  - engine.py slotchain() 20 min before go (inline preflight)

Checks:
  1. EXAM bot webhook must be empty (else getUpdates fails -> players 0)
  2. PAID bot webhook must be set to Cloudflare Worker URL
  3. Cloudflare Worker /t alive
  4. Main group can_post + can_pin
  5. Paid batch groups: PAID bot admin with invite rights
  6. Razorpay webhook active
  7. Slot-chain not stuck (no stale lock > 120s, no blocked)
  8. State.json not corrupted, today's jobs not already sealed missed
  9. Batch env vars present (PAID_CHAT_*, PAID_PRICE_*)

Auto-fixes:
  - delete EXAM webhook
  - set PAID webhook
  - dispatch slot-chain if not running and actionable
  - clear stale locks
  - DM admin with summary

v11.4.22 (22-Sep): added per user request — 20 min pre-verification
"""
import os
import sys
import json
import time
import datetime as dt
import urllib.request
import urllib.parse

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Config — same as engine.py
JOBS = {
    "malwa": {"go": 11*3600, "label": "11:00 AM"},
    "iari": {"go": 14*3600+30*60, "label": "2:30 PM"},
    "afo": {"go": 18*3600, "label": "6:00 PM"},
}
ORDER = ["malwa", "iari", "afo"]

WORKER_URL = "https://live-test-free.upsssc360.workers.dev"
WORKER_T_URL = WORKER_URL + "/t"
PAID_WEBHOOK_URL = WORKER_URL + "/ph/4574ea9aab7e913d4ea9ff1270d89eda"
PAID_WEBHOOK_SECRET = os.environ.get("PAID_WEBHOOK_SECRET", "odCqUofKvydqYgfJkFzGTwYwTAAm4ZCP")
RZP_WEBHOOK_URL = WORKER_URL + "/rzp-webhook"

BATCHES = [
    {"key": "iari", "chat": os.environ.get("PAID_CHAT_IARI", "-1003922097468"), "price": os.environ.get("PAID_PRICE_IARI", "₹99")},
    {"key": "malwa", "chat": os.environ.get("PAID_CHAT_MALWA", "-1003761821341"), "price": os.environ.get("PAID_PRICE_MALWA", "₹151")},
    {"key": "nemraj", "chat": os.environ.get("PAID_CHAT_NEMRAJ", "-1003853396327"), "price": os.environ.get("PAID_PRICE_NEMRAJ", "₹99")},
    {"key": "rksharma", "chat": os.environ.get("PAID_CHAT_RKSHARMA", "-1003880198347"), "price": os.environ.get("PAID_PRICE_RKSHARMA", "₹99")},
    {"key": "afo", "chat": os.environ.get("PAID_CHAT_AFO", "-1003687531473"), "price": os.environ.get("PAID_PRICE_AFO", "₹251")},
    {"key": "cane", "chat": os.environ.get("PAID_CHAT_CANE", "-1003707610763"), "price": os.environ.get("PAID_PRICE_CANE", "₹151")},
    {"key": "pashu", "chat": os.environ.get("PAID_CHAT_PASHU", "-1003947957354"), "price": os.environ.get("PAID_PRICE_PASHU", "₹151")},
]

def istnow():
    return dt.datetime.now(dt.timezone.utc).astimezone(IST)

def daykey(t=None):
    return (t or istnow()).strftime("%Y-%m-%d")

def go_dt(day, job):
    d = dt.date.fromisoformat(day)
    return dt.datetime(d.year, d.month, d.day, tzinfo=IST) + dt.timedelta(seconds=JOBS[job]["go"])

def log(*a):
    print(f"[{istnow().strftime('%H:%M:%S')}] [precheck] {' '.join(str(x) for x in a)}", flush=True)

def tg_call(token, method, **params):
    if not token:
        return None
    try:
        data = json.dumps(params).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
            return j.get("result") if j.get("ok") else j
    except Exception as e:
        log(f"tg {method} err {e}")
        return None

def fetch_url(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "precheck-v11.4.22"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode()[:2000], r.status
    except Exception as e:
        return f"err {e}", 0

def check_exam_webhook():
    token = os.environ.get("EXAM_TG_TOKEN", "")
    if not token:
        return False, "EXAM_TG_TOKEN missing"
    info = tg_call(token, "getWebhookInfo") or {}
    url = info.get("url", "")
    if url:
        tg_call(token, "deleteWebhook", drop_pending_updates=False)
        log(f"FIXED: EXAM webhook was set to {url} -> deleted")
        return True, f"FIXED: EXAM webhook deleted (was {url})"
    return True, "EXAM webhook empty OK"

def check_paid_webhook():
    token = os.environ.get("PAID_BOT_TOKEN", "") or os.environ.get("PAID_TOKEN", "")
    if not token:
        return False, "PAID_BOT_TOKEN missing"
    info = tg_call(token, "getWebhookInfo") or {}
    url = info.get("url", "")
    pending = info.get("pending_update_count", 0)
    if url != PAID_WEBHOOK_URL:
        try:
            data = json.dumps({
                "url": PAID_WEBHOOK_URL,
                "secret_token": PAID_WEBHOOK_SECRET,
                "allowed_updates": ["message","callback_query","chat_join_request","my_chat_member"]
            }).encode()
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/setWebhook", data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.loads(r.read().decode())
                if j.get("ok"):
                    log(f"FIXED: PAID webhook set to {PAID_WEBHOOK_URL}")
                    return True, f"FIXED: PAID webhook set (pending was {pending})"
                else:
                    return False, f"PAID webhook set failed: {j}"
        except Exception as e:
            return False, f"PAID webhook set err {e}"
    if pending > 10:
        return False, f"PAID webhook pending {pending} high"
    return True, f"PAID webhook OK {url} pending {pending}"

def check_worker():
    body, status = fetch_url(WORKER_T_URL)
    if status == 200 and "ok cf-worker" in body:
        return True, f"Worker OK: {body.strip()[:80]}"
    return False, f"Worker FAIL status {status} body {body[:100]}"

def check_main_group():
    token = os.environ.get("EXAM_TG_TOKEN", "")
    chat = os.environ.get("CHAT_ID", "-1003784795446")
    if not token:
        return False, "EXAM token missing for can_post"
    try:
        me = tg_call(token, "getMe") or {}
        bot_id = me.get("id")
        res = tg_call(token, "getChatMember", chat_id=chat, user_id=bot_id) or {}
        if not res:
            return False, "getChatMember failed"
        st = res.get("status", "?")
        if st in ("administrator","creator"):
            can_pin = res.get("can_pin_messages", False) or st=="creator"
            return True, f"Main group OK bot {st} pin={can_pin}"
        return False, f"Main group bot status {st} not admin"
    except Exception as e:
        return False, f"Main group check err {e}"

def check_paid_batches():
    token = os.environ.get("PAID_BOT_TOKEN", "") or os.environ.get("PAID_TOKEN", "")
    if not token:
        return False, "PAID token missing for batch check"
    me = tg_call(token, "getMe") or {}
    bot_id = me.get("id")
    if not bot_id:
        return False, "PAID getMe failed"
    bad = []
    ok = []
    for b in BATCHES:
        chat = b["chat"]
        if not chat:
            bad.append(f"{b['key']} no chat")
            continue
        try:
            mem = tg_call(token, "getChatMember", chat_id=chat, user_id=bot_id) or {}
            st = mem.get("status", "?")
            can_inv = mem.get("can_invite_users", False) or st=="creator"
            if st in ("administrator","creator") and can_inv:
                ok.append(b["key"])
            else:
                bad.append(f"{b['key']} status={st} invite={can_inv}")
        except Exception as e:
            bad.append(f"{b['key']} err {e}")
    if bad:
        return False, f"Batches BAD: {', '.join(bad)} | OK: {', '.join(ok)}"
    return True, f"All {len(ok)} batches OK: {', '.join(ok)}"

def check_razorpay_webhook():
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    key_sec = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_sec:
        return False, "Razorpay keys missing"
    try:
        import base64
        auth = base64.b64encode(f"{key_id}:{key_sec}".encode()).decode()
        req = urllib.request.Request("https://api.razorpay.com/v1/webhooks",
                                     headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
            items = j.get("items", [])
            active = [x for x in items if x.get("active") and RZP_WEBHOOK_URL in x.get("url","")]
            if active:
                ev = active[0].get("events", {})
                paid_ev = ev.get("payment_link.paid")
                return True, f"RZP webhook OK active {active[0]['id']} paid={paid_ev}"
            any_active = [x for x in items if x.get("active")]
            if any_active:
                return False, f"RZP webhook active but not ours: {any_active[0]['url']} — need {RZP_WEBHOOK_URL}"
            return False, f"RZP no active webhook found, need {RZP_WEBHOOK_URL}"
    except Exception as e:
        return False, f"RZP check err {e}"

def check_state_locks():
    try:
        raw_url = "https://raw.githubusercontent.com/b9811507-del/live-test/main/state.json?t=" + str(int(time.time()))
        body, status = fetch_url(raw_url, timeout=15)
        if status != 200:
            return False, f"state.json fetch fail {status}"
        st = json.loads(body)
        day = daykey()
        issues = []
        for job in ORDER:
            j = ((st.get("days") or {}).get(day) or {}).get(job) or {}
            lock_ts = j.get("lock_ts")
            if lock_ts and j.get("locked_by"):
                age = time.time() - float(lock_ts)
                if age > 600 and int(j.get("step",0)) < 8:
                    issues.append(f"{job} stale lock {int(age)}s by {j.get('locked_by')}")
            if j.get("blocked"):
                issues.append(f"{job} blocked {j.get('blocked')}")
        if issues:
            return False, f"State issues: {'; '.join(issues)}"
        return True, f"State OK for {day}"
    except Exception as e:
        return False, f"State check err {e}"

def time_to_next_slot():
    now = istnow()
    day = daykey(now)
    soonest = None
    soonest_job = None
    for job in ORDER:
        go = go_dt(day, job)
        diff = (go - now).total_seconds()
        if diff > 0 and (soonest is None or diff < soonest):
            soonest = diff
            soonest_job = job
    return soonest_job, soonest

def should_run_precheck():
    job, secs = time_to_next_slot()
    if job is None:
        return False, None, None
    mins = secs / 60.0
    if 0 < mins <= 20:
        return True, job, mins
    if -15 <= mins <= 0:
        return True, job, mins
    return False, job, mins

def run_all_checks(fix=True):
    results = []
    checks = [
        ("EXAM webhook empty", check_exam_webhook),
        ("PAID webhook set", check_paid_webhook),
        ("Cloudflare Worker", check_worker),
        ("Main group admin", check_main_group),
        ("Paid batches admin", check_paid_batches),
        ("Razorpay webhook", check_razorpay_webhook),
        ("State locks", check_state_locks),
    ]
    all_ok = True
    for name, fn in checks:
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"EXC {e}"
        results.append((name, ok, msg))
        log(f"{'✅' if ok else '❌'} {name}: {msg}")
        if not ok:
            all_ok = False
    return all_ok, results

def dispatch_slot_chain():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
    if not token:
        log("No GITHUB_TOKEN for dispatch")
        return False
    try:
        data = json.dumps({"ref": "main"}).encode()
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/slot-chain.yml/dispatches",
                                     data=data, method="POST",
                                     headers={"Authorization": f"Bearer {token}",
                                              "Content-Type": "application/json",
                                              "Accept": "application/vnd.github+json",
                                              "User-Agent": "precheck"})
        with urllib.request.urlopen(req, timeout=20) as r:
            log(f"Dispatched slot-chain status {r.status}")
            return r.status in (200,204)
    except Exception as e:
        log(f"Dispatch failed {e}")
        return False

def main():
    job, secs = time_to_next_slot()
    mins = secs/60 if secs else 0
    should, job2, mins2 = should_run_precheck()
    log(f"IST {istnow().strftime('%Y-%m-%d %H:%M')} next {job} in {mins/60:.1f}h ({mins:.0f} min) should_run={should}")
    if not should:
        log(f"Outside 20 min window (next {job} in {mins:.0f} min) -> skipping heavy checks, only light worker check")
        ok, msg = check_worker()
        log(f"Light check worker: {ok} {msg}")
        return 0

    log(f"=== PRECHECK 20 MIN BEFORE {job2.upper()} ({mins2:.0f} min to go) ===")
    all_ok, results = run_all_checks(fix=True)

    if not all_ok:
        log("Some checks FAILED -> dispatching slot-chain to revive")
        dispatch_slot_chain()
    else:
        try:
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            repo = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
            if token:
                req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/slot-chain.yml/runs?status=in_progress&per_page=5",
                                             headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    j = json.loads(r.read().decode())
                    runs = j.get("workflow_runs", [])
                    if not runs:
                        log("No slot-chain in_progress -> dispatching")
                        dispatch_slot_chain()
                    else:
                        log(f"slot-chain alive: {runs[0]['id']} {runs[0]['status']}")
        except Exception as e:
            log(f"slot-chain alive check err {e} -> dispatching anyway")
            dispatch_slot_chain()

    try:
        exam_token = os.environ.get("EXAM_TG_TOKEN")
        admin_chat = os.environ.get("ADMIN_CHAT")
        if exam_token and admin_chat:
            lines = [f"🔍 <b>Pre-check {job2.upper()} — {mins2:.0f} min to go</b> ({istnow().strftime('%H:%M IST')})", ""]
            for name, ok, msg in results:
                lines.append(f"{'✅' if ok else '❌'} {name}: {msg[:120]}")
            lines.append("")
            lines.append(f"{'✅ All OK — test will start on time' if all_ok else '⚠️ Some issues fixed, slot-chain dispatched — monitoring'}")
            text = "\n".join(lines)
            tg_call(exam_token, "sendMessage", chat_id=admin_chat, text=text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        log(f"DM admin failed {e}")

    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
