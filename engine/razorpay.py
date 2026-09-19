#!/usr/bin/env python3
"""razorpay.py — Razorpay payment links for batch enrolment (v11.3).

Why payment LINKS + polling instead of their webhook:
  * the exam platform runs entirely inside GitHub Actions — there is no public server to receive a
    webhook (the admin's old webhook host returns 503);
  * so the bot CREATES a Razorpay payment link per student (API, server-side) and then CHECKS its
    status from the keepwarm desk pass (~every 150 s). Payment confirmed -> single-use join link is
    sent into the student's chat automatically. No webhook, no server, nothing to keep alive.

API: https://api.razorpay.com/v1  (HTTP Basic: key_id:key_secret)
  POST /payment_links           -> {"id","short_url","status":"created",...}
  GET  /payment_links/{id}      -> {"status":"created"|"paid"|"expired"|"cancelled", "payments":[...]}

Secrets: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET (never logged, never printed).
Offline mode (ENGINE_FAKE=1): a local fake stands in, so the whole flow is battery-tested.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.razorpay.com/v1"
FAKE = os.environ.get("ENGINE_FAKE", "") == "1"
TIMEOUT = 30


def key_id():
    return (os.environ.get("RAZORPAY_KEY_ID", "") or "").strip()


def key_secret():
    return (os.environ.get("RAZORPAY_KEY_SECRET", "") or "").strip()


def enabled():
    return bool(key_id() and key_secret())


def _fake(method, path, body=None):
    st = _FAKE_STORE.setdefault(path.split("/")[-1] if path.startswith("/payment_links/") else "new", {})
    if method == "POST":
        n = _FAKE_STORE["n"] = _FAKE_STORE.get("n", 0) + 1
        pid = "plink_FAKE%04d" % n
        _FAKE_STORE[pid] = {"id": pid, "short_url": "https://rzp.io/rzp/FAKE%04d" % n, "status": "created",
                            "amount": (body or {}).get("amount"), "notes": (body or {}).get("notes") or {},
                            "created_at": int(time.time())}
        _FAKE_LAST["id"] = pid
        return _FAKE_STORE[pid]
    pid = path.rsplit("/", 1)[-1] or _FAKE_LAST.get("id")
    rec = _FAKE_STORE.setdefault(pid, {"id": pid, "status": os.environ.get("ENGINE_FAKE_RZP_STATUS", "created")})
    if os.environ.get("ENGINE_FAKE_RZP_STATUS"):
        rec["status"] = os.environ["ENGINE_FAKE_RZP_STATUS"]
    return rec


_FAKE_STORE = {}
_FAKE_LAST = {}


def _call(method, path, body=None):
    if FAKE:
        return _fake(method, path, body)
    if not enabled():
        return {"error": "razorpay_not_configured"}
    auth = base64.b64encode(("%s:%s" % (key_id(), key_secret())).encode()).decode()
    req = urllib.request.Request(API + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 method=method,
                                 headers={"Authorization": "Basic " + auth,
                                          "Content-Type": "application/json",
                                          "User-Agent": "agri-quiz-v11"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
        except Exception:
            err = {}
        # never include the credential or the raw body in logs
        return {"error": "http_%s" % e.code, "description": (err.get("error") or {}).get("description", "")[:160]}
    except Exception as e:
        return {"error": "exc", "description": str(e)[:120]}


def create_payment_link(batch_key, title, amount_rupees, uid, name="", callback_url="",
                        description="", expire_minutes=1440):
    """Create a per-student payment link. Returns the Razorpay JSON (contains id + short_url)."""
    amt = int(round(float(amount_rupees) * 100))
    body = {
        "amount": amt,
        "currency": "INR",
        "accept_partial": False,
        "description": (description or title)[:255],
        "customer": {"name": (name or "Student")[:60]},
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {"batch": batch_key, "uid": str(uid), "system": "agri-quiz-v11"},
        "callback_method": "get",
    }
    if callback_url:
        body["callback_url"] = callback_url
    if expire_minutes:
        body["expire_by"] = int(time.time()) + int(expire_minutes) * 60
    return _call("POST", "/payment_links", body)


def payment_status(link_id):
    d = _call("GET", "/payment_links/%s" % link_id)
    if not isinstance(d, dict) or d.get("error"):
        return {"status": "unknown", "error": d.get("error"), "description": d.get("description", "")}
    pays = d.get("payments") or []
    return {"status": (d.get("status") or "unknown").lower(),
            "amount": d.get("amount"),
            "payments": [{"id": p.get("payment_id") or p.get("id"), "status": p.get("status"),
                          "amount": p.get("amount")} for p in pays][:5],
            "raw_status": d.get("status")}


def revoke_link(link_id):
    """v11.4.14: hard rule ek payment = ek link — physically kill superseded/duplicate links."""
    return _call("POST", "/payment_links/%s/revoke" % link_id, {})


def is_paid(link_id):
    return payment_status(link_id).get("status") == "paid"


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        print("razorpay configured:", enabled(), "| key id prefix:", (key_id()[:8] + "…") if key_id() else "-")
        if enabled():
            code = _call("GET", "/payment_links?count=1")
            print("auth:", "OK" if not code.get("error") else code.get("error"))
    elif cmd == "create" and len(sys.argv) > 3:
        print(json.dumps(create_payment_link("cli", "CLI test", float(sys.argv[2]), sys.argv[3]),
                         indent=1)[:400])
    elif cmd == "status" and len(sys.argv) > 2:
        print(json.dumps(payment_status(sys.argv[2]), indent=1))
