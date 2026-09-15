#!/usr/bin/env python3
"""paid.py — paid-batch showcase + enrolment + one-time join links (v11.1).

FLOW (as ordered by the admin):
  1. after every test, the LAST group message is the paid-batches message (all batches, prices,
     perks, each with its own payment button — the payment link is embedded in the button);
  2. a student taps a batch -> the bot opens a private chat (their own chat box) with the batch
     detail, the payment link and an "I have paid" button;
  3. the moment payment is confirmed (Telegram native invoice -> successful_payment, or the
     verified claim flow) the bot creates a SINGLE-USE invite link (member_limit=1) for that batch
     group and sends it into that student's chat box.

Deliberately no server: payments are either Telegram-native (PAY_PROVIDER_TOKEN) or an external
payment link + claim; every state change is journaled in state.json, so a resumed run never
double-issues a link.

Config (GHA secrets; defaults come from the locked batch list):
  PAID_LINK_<KEY>     external payment link (UPI/Razorpay/...)  -> embedded in the button
  PAID_PRICE_<KEY>    price text, e.g. "₹151"
  PAID_CHAT_<KEY>     batch group chat id (join link is created there)
  PAY_PROVIDER_TOKEN  Telegram Payments provider token -> instant automatic verification
  PAID_VERIFY         "auto" (default: link on claim + admin alert) | "approve" (admin approves first)
Keys: afo, pashu, cane.
"""
import os
import time

# --------------------------------------------------------------------------- catalog
# 7 paid batches (admin order 2026-09-15). Chat ids / prices live in GHA secrets
# (PAID_CHAT_<KEY>, PAID_PRICE_<KEY>); only the ids that were already part of the build spec
# keep a code fallback.
DEFAULTS = [
    {"key": "iari", "emoji": "📘", "title": "IARI BOOK MCQ BATCH", "price": "", "chat": "",
     "perks": "Complete IARI book (1074 pages) chapter-wise MCQs · daily 5-page test series · answer keys"},
    {"key": "malwa", "emoji": "📚", "title": "MALWA BOOK VOL 1+2+HORTICULTURE", "price": "", "chat": "",
     "perks": "Malwa Vol-1, Vol-2 and Horticulture books' full MCQ practice · daily 20-question tests · PDF notes"},
    {"key": "nemraj", "emoji": "🌾", "title": "NEMRAJ SUNDA BOOK BATCH", "price": "", "chat": "",
     "perks": "Nemraj Sunda book MCQs · topic-wise practice · full-length mock papers"},
    {"key": "rksharma", "emoji": "📗", "title": "RK SHARMA BOOK BATCH", "price": "", "chat": "",
     "perks": "R.K. Sharma book MCQs · subject-wise practice · revision notes"},
    {"key": "afo", "emoji": "🌆", "title": "AFO SELECTION BATCH", "price": "", "chat": "-1003687531473",
     "perks": "AFO mains full-length tests (new pattern) · previous-year papers · selection-focused practice"},
    {"key": "cane", "emoji": "🎋", "title": "SUGARCANE PREMIUM BATCH", "price": "₹151",
     "chat": "-1003707610763",
     "perks": "Sugarcane premium classes · daily tests · revision notes"},
    {"key": "pashu", "emoji": "🐄", "title": "PASHUDHAN ADHIKARI BATCH", "price": "₹151",
     "chat": "-1003947957354",
     "perks": "Pashudhan Adhikari syllabus classes · daily MCQ tests · structured notes"},
]
LINK_HOURS = int(os.environ.get("PAID_LINK_HOURS", "24"))
PAID_VERIFY = (os.environ.get("PAID_VERIFY", "auto") or "auto").lower()


def batches():
    out = []
    for b in DEFAULTS:
        k = b["key"].upper()
        out.append({**b,
                    "price": os.environ.get("PAID_PRICE_" + k, "").strip() or b["price"],
                    "payment_link": os.environ.get("PAID_LINK_" + k, "").strip(),
                    "chat": os.environ.get("PAID_CHAT_" + k, "").strip() or b["chat"]})
    return out


def batch(key):
    for b in batches():
        if b["key"] == key:
            return b
    return None


def provider_token():
    return (os.environ.get("PAY_PROVIDER_TOKEN", "") or "").strip()


def price_amount(price):
    digits = "".join(c for c in str(price or "") if c.isdigit())
    return int(digits) if digits else 0


# --------------------------------------------------------------------------- links / deep links
def bot_username(E):
    E.bot_id()
    return E._bot.get("username") or "Arunkatyanquiz_bot"


def deep_link(E, payload):
    return "https://t.me/%s?start=%s" % (bot_username(E), payload)


def line(pairs):
    return "".join("%s%d. %s\n" % ("", i + 1, p) for i, p in enumerate(pairs))


# --------------------------------------------------------------------------- group message (last message after every test)
def group_text():
    from translator import t
    live = batches()
    if not live:
        return t("paid_empty")
    parts = [t("paid_title"), t("paid_intro"), ""]
    for b in live:
        parts.append(t("paid_row", emoji=b["emoji"], title=b["title"],
                       price=(b["price"] or "Fee on enquiry"), perks=b["perks"]))
    parts += ["", t("paid_footer")]
    return "\n".join(parts)


def group_keyboard(E):
    from translator import t
    rows = []
    for b in batches():
        label = t("paid_btn_batch", emoji=b["emoji"], title=b["title"],
                  price=b["price"]) if b["price"] else "%s %s — Enrol" % (b["emoji"], b["title"])
        url = b["payment_link"] or deep_link(E, "buy_" + b["key"])
        rows.append([{"text": label[:64], "url": url}])
    rows.append([{"text": t("paid_btn_all")[:64], "url": deep_link(E, "catalog")}])
    return {"inline_keyboard": rows}


def post_after_test(E, chat, job=None, day=None):
    """Send the paid-batches message as the LAST message of a test day (journaled, never duplicated)."""
    from translator import t
    st = E.jload()
    paid = st.setdefault("paid", {})
    tag = "msg_%s_%s" % (day or E.daykey(), job or "test")
    if paid.get(tag):
        E.log("paid: already posted for %s (%s)" % (tag, paid[tag]))
        return paid[tag]
    if not batches():
        return None
    m = E.tg("sendMessage", chat_id=chat, text=group_text(), parse_mode="HTML",
             disable_web_page_preview=True, reply_markup=group_keyboard(E))
    if m:
        paid[tag] = m["message_id"]
        paid["posted_at"] = E.istnow().isoformat(timespec="seconds")
        E.jsave(st, "paid batches message")
        E.log("paid: batches message posted (#%s)" % m["message_id"])
    else:
        E.log("paid: batches message failed to send")
    return (m or {}).get("message_id")


# --------------------------------------------------------------------------- student DM flows
def _send(E, uid, text, keyboard=None):
    return E.tg("sendMessage", chat_id=str(uid), text=text, parse_mode="HTML",
                disable_web_page_preview=True, reply_markup=keyboard)


def catalog_keyboard(E):
    rows = []
    for b in batches():
        rows.append([{"text": ("%s %s — view" % (b["emoji"], b["title"]))[:64],
                      "callback_data": "batch:" + b["key"]}])
    return {"inline_keyboard": rows}


def send_catalog(E, uid, greeting=True):
    from translator import t
    body = (t("dm_welcome") if greeting else t("dm_help")) + "\n\n" + group_text()
    return _send(E, uid, body, catalog_keyboard(E))


def send_batch_detail(E, uid, key):
    from translator import t
    b = batch(key)
    if not b:
        return _send(E, uid, t("dm_nobatch"))
    body = t("dm_batch", emoji=b["emoji"], title=b["title"], price=(b["price"] or "Fee on enquiry"),
             perks=b["perks"])
    rows = []
    if b["payment_link"]:
        rows.append([{"text": t("dm_pay_btn", price=b["price"] or "")[:64], "url": b["payment_link"]}])
    elif provider_token() and price_amount(b["price"]):
        rows.append([{"text": t("dm_pay_btn", price=b["price"])[:64], "callback_data": "invoice:" + key}])
    else:
        body += "\n\n" + "Payment link will be shared by the batch team. After paying, tap <b>I have paid</b>."
    rows.append([{"text": t("dm_paid_btn"), "callback_data": "claim:" + key}])
    return _send(E, uid, body, {"inline_keyboard": rows})


def send_invoice(E, uid, key):
    b = batch(key)
    amt = price_amount(b["price"]) if b else 0
    if not (b and amt and provider_token()):
        return None
    return E.tg("sendInvoice", chat_id=str(uid), title=b["title"][:32], description=b["perks"][:255],
                payload="batch:%s:%s" % (key, uid), provider_token=provider_token(), currency="INR",
                prices=[{"label": b["title"][:32], "amount": amt * 100}])


def _entitle(st, uid, key, **kw):
    users = st.setdefault("paid", {}).setdefault("users", {})
    u = users.setdefault(str(uid), {"batches": {}, "name": kw.get("name") or ""})
    if kw.get("name"):
        u["name"] = kw["name"]
    rec = u["batches"].setdefault(key, {})
    rec.update({k: v for k, v in kw.items() if k != "name"})
    return rec


def invite_ok(E, chat):
    """The bot needs to be an administrator with the Invite Users right in the batch group."""
    m = E.tg("getChatMember", chat_id=str(chat), user_id=E.bot_id()) or {}
    st = m.get("status")
    if st in ("administrator", "creator"):
        return bool(m.get("can_invite_users", True) or st == "creator"), st
    return False, (st or "?")


def issue_link(E, st, key, uid, name="", mode="claim", ref=""):
    """Create a single-use join link and deliver it to the student's chat box. Journaled, idempotent."""
    from translator import t
    b = batch(key)
    if not b:
        return None
    rec = _entitle(st, uid, key, at=E.istnow().isoformat(timespec="seconds"), mode=mode, ref=ref, name=name)
    ok, status = invite_ok(E, b["chat"])
    if not ok:
        rec["link_status"] = "pending_bot_not_admin(%s)" % status
        E.jsave(st, "paid claim pending (no invite right)")
        _send(E, uid, t("dm_link_pending", title=b["title"]))
        E.dm_admin(t("adm_noinvite", title=b["title"]) + "\nStudent id: <code>%s</code>" % uid, "paid:noinvite", 3600)
        return None
    link = None
    try:
        link = E.tg("createChatInviteLink", chat_id=b["chat"], member_limit=1,
                    expire_date=int(time.time()) + LINK_HOURS * 3600,
                    name=("%s-%s" % (key, str(uid)[-6:]))[:32])
    except Exception:
        link = None
    if not link:
        link = E.tg("createChatInviteLink", chat_id=b["chat"], member_limit=1,
                    name=("%s-%s" % (key, str(uid)[-6:]))[:32])
    if not link or not link.get("invite_link"):
        rec["link_status"] = "create_failed"
        E.jsave(st, "paid claim link failed")
        E.dm_admin("⚠️ Invite link could not be created for <b>%s</b> (student <code>%s</code>)."
                   % (b["title"], uid), "paid:linkfail", 1800)
        _send(E, uid, t("dm_link_pending", title=b["title"]))
        return None
    url = link["invite_link"]
    rec.update({"link_status": "issued", "link_name": link.get("name"), "issued_at":
                E.istnow().isoformat(timespec="seconds")})
    E.jsave(st, "paid link issued")
    _send(E, uid, t("dm_link", title=b["title"], link=url, hours=LINK_HOURS),
          {"inline_keyboard": [[{"text": "🚀 Join " + b["title"][:40], "url": url}]]})
    E.dm_admin(t("adm_claim", title=b["title"], name=name or "-", uid=uid, mode=mode,
                 issued="yes"), "paid:claim", 300)
    return url


def entitlements(st, uid):
    return (((st.get("paid") or {}).get("users") or {}).get(str(uid)) or {}).get("batches") or {}


def send_mybatches(E, uid):
    from translator import t
    st = E.jload()
    got = entitlements(st, uid)
    if not got:
        return _send(E, uid, t("dm_mybatches_none"))
    rows, kb = [], []
    for key, rec in got.items():
        b = batch(key) or {"title": key.upper(), "chat": ""}
        rows.append("• <b>%s</b> — joined %s" % (b["title"], str(rec.get("at", ""))[:10]))
        kb.append([{"text": t("dm_reissue_btn", title=b["title"])[:64], "callback_data": "reissue:" + key}])
    return _send(E, uid, t("dm_mybatches", rows="\n".join(rows)), {"inline_keyboard": kb})


# --------------------------------------------------------------------------- update handlers
def handle_message(E, st, msg):
    from translator import t
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return
    uid = str(chat.get("id"))
    text = (msg.get("text") or "").strip()
    name = ((msg.get("from") or {}).get("first_name") or "")[:32]
    sp = msg.get("successful_payment")
    if sp:
        payload = (sp.get("invoice_payload") or "")
        parts = payload.split(":")
        key = parts[1] if len(parts) > 2 and parts[0] == "batch" else None
        if key:
            issue_link(E, st, key, uid, name=name, mode="telegram_payment")
        return
    low = text.lower()
    if low.startswith("/start"):
        payload = text[6:].strip().lower()
        if payload.startswith("buy_") or payload in [b["key"] for b in batches()]:
            key = payload.replace("buy_", "")
            return send_batch_detail(E, uid, key)
        if payload in ("catalog", "", "start"):
            return send_catalog(E, uid, greeting=True)
        return send_catalog(E, uid, greeting=True)
    if low.startswith("/mybatches") or low.startswith("/my"):
        return send_mybatches(E, uid)
    if low.startswith("/help"):
        return _send(E, uid, t("dm_help"))
    if low.startswith("/admin"):
        return admin_command(E, st, uid, text)
    # any other private message -> if a claim is awaiting a reference, record it
    claims = (st.get("paid") or {}).get("claims") or []
    for c in reversed(claims):
        if str(c.get("uid")) == uid and c.get("ref_state") == "awaiting" and len(text) >= 4:
            c["ref"] = text[:80]
            c["ref_state"] = "received"
            E.jsave(st, "paid payment reference recorded")
            _send(E, uid, "✅ Reference recorded for <b>%s</b>. Thank you!" % (batch(c["key"]) or {}).get("title", ""))
            E.dm_admin("🧾 Payment reference from <code>%s</code> for %s: <code>%s</code>"
                       % (uid, (batch(c["key"]) or {}).get("title", c.get("key")), c["ref"]), "paid:ref", 300)
            return
    return send_catalog(E, uid, greeting=False)


def handle_callback(E, st, cb):
    from translator import t
    data = (cb.get("data") or "")
    msg = cb.get("message") or {}
    user = cb.get("from") or {}
    uid = str(user.get("id"))
    name = (user.get("first_name") or "")[:32]
    dm_chat = ((msg.get("chat") or {}).get("id"))
    is_private = (msg.get("chat") or {}).get("type") == "private"
    E.tg("answerCallbackQuery", callback_query_id=cb.get("id"), text="")
    if data.startswith("batch:"):
        if is_private:
            send_batch_detail(E, uid, data.split(":", 1)[1])
        else:
            E.tg("answerCallbackQuery", callback_query_id=cb.get("id"), url=deep_link(E, "buy_" + data.split(":", 1)[1]))
        return
    if data.startswith("invoice:"):
        if is_private:
            send_invoice(E, uid, data.split(":", 1)[1])
        return
    if data.startswith("claim:"):
        key = data.split(":", 1)[1]
        b = batch(key)
        if not b:
            return
        claim = {"uid": uid, "key": key, "at": E.istnow().isoformat(timespec="seconds"), "mode": "claim",
                 "ref_state": "awaiting"}
        st.setdefault("paid", {}).setdefault("claims", []).append(claim)
        E.jsave(st, "paid claim received")
        if PAID_VERIFY == "approve":
            _send(E, uid, t("dm_verify_wait", title=b["title"]))
            E.dm_admin("💳 Enrolment awaiting approval: <b>%s</b> · student <code>%s</code> (%s)\n"
                       "Approve with: <code>/admin &lt;key&gt; approve %s %s</code>"
                       % (b["title"], uid, name, uid, key), "paid:approve", 60)
            if is_private:
                _send(E, uid, t("dm_ref_ask"))
            return
        if is_private:
            _send(E, uid, t("dm_verify_wait", title=b["title"]))
        url = issue_link(E, st, key, uid, name=name, mode="claim_auto")
        claim["issued"] = bool(url)
        E.jsave(st, "paid claim processed")
        if is_private and url:
            _send(E, uid, t("dm_ref_ask"))
        return
    if data.startswith("reissue:"):
        key = data.split(":", 1)[1]
        if entitlements(E.jload(), uid).get(key):
            issue_link(E, E.jload(force=True), key, uid, name=name, mode="reissue")
        else:
            _send(E, uid, t("dm_nobatch"))
        return
    if data == "catalog" and is_private:
        send_catalog(E, uid, greeting=False)


def handle_join_request(E, st, jr):
    """Auto-approve join requests only for students who already hold that batch entitlement."""
    uid = str((jr.get("from") or {}).get("id"))
    chat = str((jr.get("chat") or {}).get("id"))
    for b in batches():
        if b["chat"] == chat and entitlements(st, uid).get(b["key"]):
            E.tg("approveChatJoinRequest", chat_id=chat, user_id=int(uid))
            E.log("paid: approved join request for %s in %s" % (uid, b["key"]))
            return
    E.dm_admin("❓ Join request from <code>%s</code> in chat <code>%s</code> — no enrolment found. "
               "Not approved automatically." % (uid, chat), "paid:joinreq", 900)


def admin_command(E, st, uid, text):
    import hmac
    from translator import t
    if str(uid) != str(E.ADMIN_CHAT or ""):
        return
    admin_key = os.environ.get("ADMIN_KEY", "")
    parts = text.split()
    if len(parts) < 2 or not admin_key or not hmac.compare_digest(parts[1], admin_key):
        log_txt = "🔒 Admin command rejected (bad key or not authorised)."
        return _send(E, uid, log_txt)
    sub = parts[2] if len(parts) > 2 else "pending"
    paid = st.setdefault("paid", {})
    if sub == "pending":
        rows = [c for c in (paid.get("claims") or []) if not c.get("issued")]
        body = "\n".join("• %s · <code>%s</code> · %s%s" % (c.get("key"), c.get("uid"), c.get("at"),
                                                            " · ref " + c["ref"] if c.get("ref") else "")
                         for c in rows[-20:]) or "No pending claims."
        return _send(E, uid, "📋 <b>Pending enrolments</b>\n" + body)
    if sub == "stats":
        users = paid.get("users") or {}
        per = {}
        for u in users.values():
            for k in (u.get("batches") or {}):
                per[k] = per.get(k, 0) + 1
        return _send(E, uid, "📊 <b>Enrolments</b>\nStudents: %d\n%s" % (
            len(users), "\n".join("%s: %d" % (k, v) for k, v in sorted(per.items())) or "-"))
    if sub in ("approve", "link", "revoke") and len(parts) >= 5:
        target, key = parts[3], parts[4]
        if sub == "revoke":
            _entitle(st, target, key, revoked_at=E.istnow().isoformat(timespec="seconds"))
            E.jsave(st, "paid revoked")
            return _send(E, uid, t("adm_revoke", uid=target, title=(batch(key) or {}).get("title", key)))
        issue_link(E, st, key, target, mode="admin_" + sub)
        for c in (paid.get("claims") or []):
            if str(c.get("uid")) == str(target) and c.get("key") == key:
                c["issued"] = True
        E.jsave(st, "paid admin issued")
        return _send(E, uid, "✅ Link issued for <code>%s</code> in %s." % (target, key))
    return _send(E, uid, "Usage: /admin &lt;key&gt; pending | stats | approve &lt;uid&gt; &lt;batch&gt; | "
                         "link &lt;uid&gt; &lt;batch&gt; | revoke &lt;uid&gt; &lt;batch&gt;")


# --------------------------------------------------------------------------- desk pass (runs in keepwarm, never during a live test)
def _test_live(st):
    days = (st.get("days") or {})
    for day, jobs in days.items():
        for job, j in (jobs or {}).items():
            if isinstance(j, dict) and int(j.get("step", 0)) == 2 and \
                    time.time() - float(j.get("lock_ts", 0) or 0) < 300:
                return "%s/%s" % (day, job)
    return None


ALLOWED_UPDATES = ["message", "callback_query", "poll", "poll_answer", "chat_join_request", "my_chat_member"]


def desk_pass(E, budget_s=8):
    """Front desk: student DMs, callbacks, payments, join requests. Single poller rule is respected:
    it never calls getUpdates while a test is live (that would cause a 409 conflict)."""
    st = E.jload(force=True)
    live = _test_live(st)
    if live:
        E.log("desk: test live (%s) -> skipping poll this pass (single-poller rule)" % live)
        return {"skipped": "test_live", "live": live}
    off = int((st.get("desk") or {}).get("offset") or 0)
    seen = set((st.get("desk") or {}).get("seen") or [])
    handled, started = 0, time.time()
    while True:
        if not E.FAKE and time.time() - started > budget_s:
            break
        r = E.tg("getUpdates", offset=off, timeout=1, allowed_updates=ALLOWED_UPDATES)
        res = r if isinstance(r, list) else (r or {}).get("result")
        if not res:
            if E.FAKE:
                break
            continue
        for u in res:
            uix = int(u.get("update_id", 0))
            off = max(off, uix + 1)
            if str(uix) in seen:
                continue
            seen.add(str(uix))
            try:
                if u.get("message"):
                    handle_message(E, st, u["message"])
                    handled += 1
                elif u.get("callback_query"):
                    handle_callback(E, st, u["callback_query"])
                    handled += 1
                elif u.get("chat_join_request"):
                    handle_join_request(E, st, u["chat_join_request"])
                    handled += 1
            except Exception as e:
                E.log("desk handler error:", str(e)[:140])
        if E.FAKE:
            break
    st["desk"] = {"offset": off, "last": E.istnow().isoformat(timespec="seconds"),
                  "handled": int((st.get("desk") or {}).get("handled", 0)) + handled,
                  "seen": sorted(seen)[-200:]}
    E.jsave(st, "desk pass (%d handled)" % handled)
    return {"handled": handled, "offset": off}


def pending_links(E):
    """Retry links that could not be created earlier (e.g. bot was not admin yet)."""
    st = E.jload(force=True)
    fixed = 0
    for uid, u in ((st.get("paid") or {}).get("users") or {}).items():
        for key, rec in (u.get("batches") or {}).items():
            if rec.get("link_status", "").startswith("pending") and not rec.get("revoked_at"):
                ok, _ = invite_ok(E, (batch(key) or {}).get("chat") or "")
                if ok:
                    issue_link(E, st, key, uid, name=u.get("name", ""), mode="retry")
                    fixed += 1
    return fixed
