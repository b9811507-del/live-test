#!/usr/bin/env python3
"""One-shot patch v11.3 — Razorpay payment-link flow (admin order 2026-09-15).

student taps a batch in the group -> bot DM -> "Pay ₹X" -> the bot CREATES a Razorpay payment link
for that student (API) -> student pays -> the keepwarm desk pass sees status=paid within ~150 s ->
single-use join link lands in the student's chat. No webhook, no server.
"""
import sys

P = "engine/paid.py"
s = open(P, encoding="utf-8").read()


def rep(old, new, label):
    global s
    if old not in s:
        print("MISSING ANCHOR:", label, "|", old.splitlines()[0][:70])
        sys.exit(1)
    s = s.replace(old, new, 1)


# ---------- imports / config
rep('''import os
import time''', '''import os
import time

import razorpay''', "import razorpay")

rep('''LINK_HOURS = int(os.environ.get("PAID_LINK_HOURS", "24"))
PAID_VERIFY = (os.environ.get("PAID_VERIFY", "auto") or "auto").lower()''',
    '''LINK_HOURS = int(os.environ.get("PAID_LINK_HOURS", "24"))
PAID_VERIFY = (os.environ.get("PAID_VERIFY", "auto") or "auto").lower()
RAZORPAY_LINK_MINUTES = int(os.environ.get("RAZORPAY_LINK_MINUTES", "1440"))   # payment link expiry (24h)
RZP_POLL_MAX_AGE_H = int(os.environ.get("RZP_POLL_MAX_AGE_H", "24"))           # stop polling after this''',
    "config")

# ---------- batch detail: add the Pay button (Razorpay) before the claim button
rep('''    rows = []
    if b["payment_link"]:
        rows.append([{"text": t("dm_pay_btn", price=b["price"] or "")[:64], "url": b["payment_link"]}])
    elif provider_token() and price_amount(b["price"]):
        rows.append([{"text": t("dm_pay_btn", price=b["price"])[:64], "callback_data": "invoice:" + key}])
    else:
        body += "\\n\\n" + "Payment link will be shared by the batch team. After paying, tap <b>I have paid</b>."''',
    '''    rows = []
    if b["payment_link"]:
        rows.append([{"text": t("dm_pay_btn", price=b["price"] or "")[:64], "url": b["payment_link"]}])
    elif razorpay.enabled() and price_amount(b["price"]):
        # v11.3: the bot creates a personal Razorpay payment link for this student
        rows.append([{"text": ("💳 Pay %s — Razorpay" % b["price"])[:64], "callback_data": "rzp:" + key}])
    elif provider_token() and price_amount(b["price"]):
        rows.append([{"text": t("dm_pay_btn", price=b["price"])[:64], "callback_data": "invoice:" + key}])
    else:
        body += "\\n\\n" + "Payment link will be shared by the batch team. After paying, tap <b>I have paid</b>."''',
    "dm batch detail")

# ---------- new strings
OPEN = '''def _entitle(st, uid, key, **kw):'''
NEW = '''def create_razorpay_link(E, st, key, uid, name=""):
    """Create a personal Razorpay payment link for this student, journal it and DM the button."""
    from translator import t
    b = batch(key)
    if not (b and razorpay.enabled()):
        return None
    amt = price_amount(b["price"])
    if amt <= 0:
        return None
    cb = deep_link(E, "paid_" + key)
    d = razorpay.create_payment_link(key, b["title"], amt, uid, name=name, callback_url=cb,
                                     description="%s — enrolment" % b["title"],
                                     expire_minutes=RAZORPAY_LINK_MINUTES)
    if not isinstance(d, dict) or not d.get("id"):
        E.log("razorpay link failed:", str(d)[:120])
        E.dm_admin("⚠️ Razorpay payment link creation failed for <b>%s</b> (student <code>%s</code>): %s"
                   % (b["title"], uid, str(d.get("description") or d.get("error"))[:120]), "rzp:fail", 1800)
        return None
    links = st.setdefault("paid", {}).setdefault("links", {})
    links[d["id"]] = {"uid": str(uid), "key": key, "amount": amt, "title": b["title"], "name": name,
                      "short_url": d.get("short_url"), "status": "created",
                      "at": E.istnow().isoformat(timespec="seconds"), "created_ts": int(time.time())}
    E.jsave(st, "razorpay link created (%s)" % d["id"])
    paid_msg = t("dm_rzp_created", title=b["title"], price=b["price"],
                 mins=max(5, RAZORPAY_LINK_MINUTES))
    _send(E, str(uid), paid_msg,
          {"inline_keyboard": [[{"text": ("💳 Pay %s now" % b["price"])[:64], "url": d["short_url"]}],
                               [{"text": t("dm_paid_btn"), "callback_data": "claim:" + key}]]})
    E.log("razorpay link %s created for %s/%s" % (d["id"], key, uid))
    return d["id"]


def verify_payments(E, st=None, limit=25):
    """Desk pass step: check every open payment link; on 'paid' issue the one-time join link."""
    from translator import t
    st = st if st is not None else E.jload(force=True)
    links = ((st.get("paid") or {}).get("links") or {})
    now = time.time()
    checked = issued = expired = 0
    for lid, rec in list(links.items()):
        if rec.get("status") == "paid" or rec.get("link_issued"):
            continue
        age_h = (now - float(rec.get("created_ts") or now)) / 3600.0
        if age_h > RZP_POLL_MAX_AGE_H:
            rec["status"] = rec.get("status") or "stale"
            continue
        if checked >= limit:
            break
        r = razorpay.payment_status(lid)
        checked += 1
        stt = r.get("status")
        if stt == "paid":
            rec["status"] = "paid"
            rec["paid_at"] = E.istnow().isoformat(timespec="seconds")
            rec["payment_id"] = (r.get("payments") or [{}])[0].get("id")
            E.jsave(st, "payment confirmed %s" % lid)
            _send(E, rec["uid"], t("dm_payment_received", title=rec["title"],
                                   amount=rec["amount"] // 100 if rec.get("amount") else ""))
            url = issue_link(E, st, rec["key"], rec["uid"], name=rec.get("name", ""), mode="razorpay")
            rec["link_issued"] = bool(url)
            E.jsave(st, "razorpay enrolment completed %s" % lid)
            issued += 1
        elif stt in ("expired", "cancelled"):
            rec["status"] = stt
            E.jsave(st, "payment link %s %s" % (lid, stt))
            _send(E, rec["uid"], t("dm_rzp_expired", title=rec["title"]),
                  {"inline_keyboard": [[{"text": ("💳 Pay %s again" % b_price(rec["key"]))[:64],
                                        "callback_data": "rzp:" + rec["key"]}]]})
            expired += 1
    if checked or issued or expired:
        E.log("desk payments: checked=%d paid=%d expired=%d" % (checked, issued, expired))
    return {"checked": checked, "issued": issued, "expired": expired}


def b_price(key):
    b = batch(key) or {}
    return b.get("price") or ""


def _entitle(st, uid, key, **kw):'''
rep(OPEN, NEW, "razorpay functions")

# ---------- callback: rzp:<key>  +  start payload paid_<key>
rep('''    if data.startswith("invoice:"):''', '''    if data.startswith("rzp:"):
        if is_private:
            create_razorpay_link(E, st, data.split(":", 1)[1], uid, name=name)
        else:
            E.tg("answerCallbackQuery", callback_query_id=cb.get("id"),
                 url=deep_link(E, "buy_" + data.split(":", 1)[1]))
        return
    if data.startswith("invoice:"):''', "rzp callback")

rep('''    if low.startswith("/start"):
        payload = text[6:].strip().lower()''', '''    if low.startswith("/start"):
        payload = text[6:].strip().lower()
        if payload.startswith("paid_"):
            # returned from the Razorpay page: verify immediately (and DM the link if already paid)
            key = payload.replace("paid_", "")
            verify_payments(E, st, limit=25)
            return send_batch_detail(E, uid, key)''', "start paid_ payload")

# ---------- desk pass: run the payment verification every pass
rep('''        elif u.get("chat_join_request"):
                    handle_join_request(E, st, u["chat_join_request"])
                    handled += 1''',
    '''        elif u.get("chat_join_request"):
                    handle_join_request(E, st, u["chat_join_request"])
                    handled += 1''', "noop keep")
rep('''    st["desk"] = {"offset": off, "last": E.istnow().isoformat(timespec="seconds"),
                  "handled": int((st.get("desk") or {}).get("handled", 0)) + handled,
                  "seen": sorted(seen)[-200:]}
    E.jsave(st, "desk pass (%d handled)" % handled)
    return {"handled": handled, "offset": off}''',
    '''    pay = verify_payments(E, st)
    st = E.jload(force=True)
    st["desk"] = {"offset": off, "last": E.istnow().isoformat(timespec="seconds"),
                  "handled": int((st.get("desk") or {}).get("handled", 0)) + handled,
                  "payments": pay,
                  "seen": sorted(seen)[-200:]}
    E.jsave(st, "desk pass (%d handled, %s payments)" % (handled, pay))
    return {"handled": handled, "offset": off, "payments": pay}''', "desk verify hook")

# ---------- /mybatches: also show unpaid links
rep('''    got = entitlements(st, uid)
    if not got:
        return _send(E, uid, t("dm_mybatches_none"))''',
    '''    got = entitlements(st, uid)
    open_links = [(lid, r) for lid, r in ((st.get("paid") or {}).get("links") or {}).items()
                  if str(r.get("uid")) == str(uid) and r.get("status") not in ("paid", "expired", "cancelled")]
    if not got and not open_links:
        return _send(E, uid, t("dm_mybatches_none"))
    if open_links:
        lid, r = open_links[-1]
        _send(E, uid, "⏳ Pending payment for <b>%s</b> — %s" % (r.get("title"), r.get("short_url") or ""), None)''',
    "mybatches pending")

open(P, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- translator strings
P = "engine/translator.py"
t = open(P, encoding="utf-8").read()
t = t.replace('''    "dm_mybatches": "📚 <b>Your enrolments</b>\\n%(rows)s",''',
'''    "dm_mybatches": "📚 <b>Your enrolments</b>\\n%(rows)s",
    "dm_rzp_created": ("🧾 <b>Payment link ready — %(title)s</b>\\n"
                       "Amount: <b>%(price)s</b> · this link is personal to you and expires in %(mins)s minutes.\\n\\n"
                       "1) Tap <b>Pay now</b> and complete the payment.\\n"
                       "2) Your one-time join link will arrive in this chat automatically (usually within 3 minutes).\\n"
                       "If you have already paid, you can also tap <b>I have paid</b>."),
    "dm_payment_received": "✅ <b>Payment received — %(title)s</b>\\nThank you! Your join link is being prepared…",
    "dm_rzp_expired": ("⌛ <b>Payment link expired — %(title)s</b>\\n"
                       "No problem — tap below to get a fresh payment link."),''')
open(P, "w", encoding="utf-8").write(t)

# ---------------------------------------------------------------- workflows: razorpay env
for wf, anchor in ((".github/workflows/slot-chain.yml", "      PAID_VERIFY: ${{ secrets.PAID_VERIFY }}"),
                   (".github/workflows/keepwarm-agent.yml", "      PAID_VERIFY: ${{ secrets.PAID_VERIFY }}")):
    w = open(wf, encoding="utf-8").read()
    if "RAZORPAY_KEY_ID" not in w:
        w = w.replace(anchor, anchor + '''
      # Razorpay payment links (v11.3)
      RAZORPAY_KEY_ID: ${{ secrets.RAZORPAY_KEY_ID }}
      RAZORPAY_KEY_SECRET: ${{ secrets.RAZORPAY_KEY_SECRET }}''')
        open(wf, "w", encoding="utf-8").write(w)
print("v11.3 patch ok: razorpay flow wired")
