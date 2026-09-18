#!/usr/bin/env python3
"""paid.py — paid-batch showcase + enrolment + one-time join links (v11.1).

FLOW (as ordered by the admin):
  1. after every test, the LAST group message is the paid-batches message (all batches, prices,
     perks, each with its own payment button — the payment link is embedded in the button);
  2. a student taps a batch -> the bot opens a private chat (their own chat box) with the batch
     detail and the personal payment link (claims retired v11.4.12);
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

import razorpay

# --------------------------------------------------------------------------- catalog
# 7 paid batches (admin order 2026-09-15). Chat ids / prices live in GHA secrets
# (PAID_CHAT_<KEY>, PAID_PRICE_<KEY>); only the ids that were already part of the build spec
# keep a code fallback.
DEFAULTS = [
    {"key": "iari", "emoji": "📘", "title": "IARI BOOK MCQ BATCH", "price": "₹99", "chat": "",
     "perks": "Complete IARI book (1074 pages) chapter-wise MCQs · daily 5-page test series · "
              "answer keys · unlimited attempts with best explanation"},
    {"key": "malwa", "emoji": "📚", "title": "MALWA BOOK VOL 1+2+HORTICULTURE", "price": "₹151", "chat": "",
     "perks": "Malwa Vol-1, Vol-2 and Horticulture books' full MCQ practice · daily 20-question tests · "
              "PDF notes · unlimited attempts with best explanation"},
    {"key": "nemraj", "emoji": "🌾", "title": "NEMRAJ SUNDA BOOK BATCH", "price": "₹99", "chat": "",
     "perks": "Nemraj Sunda book MCQs · topic-wise practice · full-length mock papers · "
              "unlimited attempts with best explanation"},
    {"key": "rksharma", "emoji": "📗", "title": "RK SHARMA BOOK BATCH", "price": "₹99", "chat": "",
     "perks": "R.K. Sharma book MCQs · subject-wise practice · revision notes · "
              "unlimited attempts with best explanation"},
    {"key": "afo", "emoji": "🌆", "title": "AFO SELECTION BATCH", "price": "₹251", "chat": "-1003687531473",
     "perks": "AFO mains full-length tests (new pattern) · previous-year papers · selection-focused "
              "practice · unlimited attempts with best explanation"},
    {"key": "cane", "emoji": "🎋", "title": "SUGARCANE PREMIUM BATCH", "price": "₹151",
     "chat": "-1003707610763",
     "perks": "Sugarcane premium classes · daily tests · revision notes · "
              "unlimited attempts with best explanation"},
    {"key": "pashu", "emoji": "🐄", "title": "PASHUDHAN ADHIKARI BATCH", "price": "₹151",
     "chat": "-1003947957354",
     "perks": "Pashudhan Adhikari syllabus classes · daily MCQ tests · structured notes · "
              "unlimited attempts with best explanation"},
]
LINK_HOURS = int(os.environ.get("PAID_LINK_HOURS", "24"))
PAID_VERIFY = (os.environ.get("PAID_VERIFY", "auto") or "auto").lower()

# v11.4.13 (admin speed order 18-Sep): webhook mode -> Telegram pushes updates to web.py /ph route,
# which spools them here; spool_drain answers instantly. getUpdates polling is switched off then.
WEBHOOK_MODE = (os.environ.get("PAID_WEBHOOK", "off") or "off").lower() in ("on", "1", "yes")
SPOOL = os.environ.get("PAID_SPOOL") or "/tmp/agri_paid_spool.jsonl"
RAZORPAY_LINK_MINUTES = int(os.environ.get("RAZORPAY_LINK_MINUTES", "1440"))   # payment link expiry (24h)
RZP_POLL_MAX_AGE_H = int(os.environ.get("RZP_POLL_MAX_AGE_H", "24"))           # stop polling after this


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


# --------------------------------------------------------------------------- paid-desk bot (separate
# from the exam bot on purpose: payment/DM traffic never shares fate with the live-test bot)
PAID_TOKEN = (os.environ.get("PAID_BOT_TOKEN") or os.environ.get("PAID_TOKEN") or "").strip()
PAID_API = "https://api.telegram.org/bot" + PAID_TOKEN


def ptg(E, method, tries=5, **params):
    """Telegram call for the paid-desk bot. Falls back to the exam bot (E.tg) automatically when
    PAID_BOT_TOKEN/PAID_TOKEN is not configured, so this is a no-op change until the secret is set."""
    if not PAID_TOKEN:
        return E.tg(method, tries=tries, **params)
    params = {k: v for k, v in params.items() if v is not None}
    if E.FAKE:
        return E._fake_tg(method, params)
    import json as _json
    import time as _time
    import urllib.error as _ue
    import urllib.request as _ur
    last = ""
    for _ in range(tries):
        try:
            data = _json.dumps(params).encode()
            req = _ur.Request(PAID_API + "/" + method, data=data,
                              headers={"Content-Type": "application/json", "User-Agent": "agri-quiz-v11-paid"})
            r = _json.loads(_ur.urlopen(req, timeout=30).read().decode())
            if r.get("ok"):
                return r["result"]
            desc = str(r.get("description", ""))
            last = desc
            if r.get("error_code") == 429:
                wait = int((r.get("parameters") or {}).get("retry_after", 3)) + 1
                E.log("ptg 429 %s -> sleep %ss" % (method, wait))
                _time.sleep(wait)
                continue
            E.log("ptg err %s: %s" % (method, desc[:140]))
            if any(x in desc.lower() for x in ("not enough rights", "chat not found", "bot was kicked")):
                return None
            _time.sleep(1.5)
        except _ue.HTTPError as e:
            last = "HTTP %s" % e.code
            _time.sleep(2)
        except Exception as e:
            last = str(e)[:120]
            E.log("ptg exc %s: %s" % (method, last))
            _time.sleep(3)
    E.log("ptg give-up %s (%s)" % (method, last[:80]))
    return None


# --------------------------------------------------------------------------- links / deep links
def bot_username(E):
    if PAID_TOKEN:
        me = ptg(E, "getMe")
        if me and me.get("username"):
            return me["username"]
    E.bot_id()
    return E._bot.get("username") or "Arunkatyanquiz_bot"


def deep_link(E, payload):
    return "https://t.me/%s?start=%s" % (bot_username(E), payload)


def line(pairs):
    return "".join("%s%d. %s\n" % ("", i + 1, p) for i, p in enumerate(pairs))


# --------------------------------------------------------------------------- group message (last message after every test)
def group_text():
    return (
        "\U0001F393 <b>ALL PAID BATCHES</b> \u2014 AGRI QUIZ WORLD\n\n"
        "Complete book-wise courses \u00b7 full test series \u00b7 expert-vetted MCQ banks \u00b7 PDF library access.\n"
        "\u267E\uFE0F <b>Unlimited attempts</b> \u00b7 \u23F3 <b>Lifetime validity</b> \u2014 pay once, the batch is yours for life.\n\n"
        "\U0001F449 <i>Touch the button below for the full batch list, fees and instant join.</i>"
    )



def group_keyboard(E):
    return {"inline_keyboard": [[{"text": "\U0001F4F2 Touch for more information", "url": deep_link(E, "catalog")}]]}


def post_after_test(E, chat, job=None, day=None):
    """Send the paid-batches message as the LAST message of a test (journaled, never duplicated).
    v11.3: one paid message per IST day -> the superseded message of an earlier test is deleted first
    (locked hygiene rule: never two copies of the same data)."""
    from translator import t
    st = E.jload()
    paid = st.setdefault("paid", {})
    day = day or E.daykey()
    if not batches():
        return None
    # ONE stable "All Paid Batches" message per day: if today's is already up, leave it
    # (admin order 2026-09-18: single professional group message, never duplicates/flicker)
    prev = paid.get("day_%s" % day) or {}
    prev_id = prev.get("id")
    if prev_id:
        paid["msg_%s_%s" % (day, job or "test")] = prev_id
        E.log("paid: reusing today's message #%s" % prev_id)
        return prev_id
    tag = "msg_%s_%s" % (day, job or "test")
    m = ptg(E, "sendMessage", chat_id=chat, text=group_text(), parse_mode="HTML",
             disable_web_page_preview=True, reply_markup=group_keyboard(E))
    if m:
        paid[tag] = m["message_id"]
        paid["day_%s" % day] = {"id": m["message_id"], "job": job, "at": E.istnow().isoformat(timespec="seconds")}
        paid["posted_at"] = E.istnow().isoformat(timespec="seconds")
        E.jsave(st, "paid batches message")
        E.log("paid: batches message posted (#%s, superseded %s)" % (m["message_id"], prev_id))
    else:
        E.log("paid: batches message failed to send")
    return (m or {}).get("message_id")


# --------------------------------------------------------------------------- student DM flows
def _send(E, uid, text, keyboard=None):
    return ptg(E, "sendMessage", chat_id=str(uid), text=text, parse_mode="HTML",
                disable_web_page_preview=True, reply_markup=keyboard)


def catalog_keyboard(E):
    rows = []
    for b in batches():
        amt = price_amount(b["price"])
        label = ("\U0001F4B3 Pay & Join \u2014 %s" % (b["price"] or "enquire"))[:64]
        cb = "rzp:" + b["key"] if (amt and razorpay.enabled()) else "batch:" + b["key"]
        rows.append([{"text": label, "callback_data": cb}])
    return {"inline_keyboard": rows}


def send_catalog(E, uid, greeting=True):
    """v11.4.11 (admin order 18-Sep): ONE message per batch — batch name + price + validity
    with its OWN 'Pay & Join' button directly underneath. No wall of buttons at the bottom."""
    if not batches():
        return _send(E, uid, "No batches are open right now \u2014 please check back soon.")
    intro = ("\U0001F44B <b>AGRI QUIZ WORLD \u2014 Paid Batches</b>\n\n"
             "Har batch me: \u267E\uFE0F <b>Unlimited attempts</b> \u00b7 \u23F3 <b>Lifetime validity</b> "
             "\u00b7 pay once, yours for life.\n"
             "Neeche apne batch ke button \u2014 <b>Pay &amp; Join</b> \u2014 dabaiye; turant aapka personal "
             "Razorpay link khulega, payment verify hote hi <b>one-time join link</b> yahin aayega.") if greeting \
            else "Pick your batch \u2014 tap <b>Pay &amp; Join</b> below it:"
    _send(E, uid, intro)
    last = None
    for b in batches():
        body = ("%s <b>%s</b>\n\nFee: <b>%s</b>\n\u267E\uFE0F Unlimited attempts \u00b7 \u23F3 Lifetime validity \u00b7 instant join after payment"
                % (b["emoji"], b["title"], b["price"] or "Fee on enquiry"))
        if b.get("perks"):
            body += "\n\n" + b["perks"]
        amt = price_amount(b["price"])
        if b["payment_link"]:
            kb = {"inline_keyboard": [[{"text": ("\U0001F4B3 Pay & Join \u2014 %s" % (b["price"] or ""))[:64],
                                        "url": b["payment_link"]}]]}
        elif amt and razorpay.enabled():
            kb = {"inline_keyboard": [[{"text": ("\U0001F4B3 Pay & Join \u2014 %s" % b["price"])[:64],
                                        "callback_data": "rzp:" + b["key"]}]]}
        elif amt and provider_token():
            kb = {"inline_keyboard": [[{"text": ("\U0001F4B3 Pay & Join \u2014 %s" % b["price"])[:64],
                                        "callback_data": "invoice:" + b["key"]}]]}
        else:
            kb = {"inline_keyboard": [[{"text": "\u2139\uFE0F View & manual enrol", "callback_data": "batch:" + b["key"]}]]}
        last = _send(E, uid, body, kb)
    _send(E, uid, "\u2753 Koi sawal ho to yahin reply kariye \u2014 team ek message door hai. Apne batches dekhne ke liye: /mybatches")
    return last


def send_batch_detail(E, uid, key):
    b = batch(key)
    if not b:
        return _send(E, uid, "This batch is not open right now \u2014 tap a batch from /start to see what\u2019s available.")
    body = ("%s <b>%s</b>\n\nFee: <b>%s</b> \u00b7 \u267E\uFE0F <b>Unlimited attempts</b> \u00b7 \u23F3 <b>Lifetime validity</b>"
            % (b["emoji"], b["title"], b["price"] or "Fee on enquiry"))
    if b.get("perks"):
        body += "\n\n" + b["perks"]
    body += "\n\n\U0001F449 Tap <b>Pay &amp; Join</b> \u2014 you get a personal Razorpay link instantly; the moment payment is verified your one-time join link arrives in this chat."
    rows = []
    if b["payment_link"]:
        rows.append([{"text": ("\U0001F4B3 Pay & Join \u2014 %s" % (b["price"] or ""))[:64], "url": b["payment_link"]}])
    elif razorpay.enabled() and price_amount(b["price"]):
        rows.append([{"text": ("\U0001F4B3 Pay & Join \u2014 %s" % b["price"])[:64], "callback_data": "rzp:" + key}])
    elif provider_token() and price_amount(b["price"]):
        rows.append([{"text": ("\U0001F4B3 Pay & Join \u2014 %s" % b["price"])[:64], "callback_data": "invoice:" + key}])
    # v11.4.12 (admin order 18-Sep): "I have paid / manual claim" removed everywhere —
    # access only via the personal payment link; no button can enrol a student unprompted.
    return _send(E, uid, body, {"inline_keyboard": rows} if rows else None)


def send_invoice(E, uid, key):
    b = batch(key)
    amt = price_amount(b["price"]) if b else 0
    if not (b and amt and provider_token()):
        return None
    return ptg(E, "sendInvoice", chat_id=str(uid), title=b["title"][:32], description=b["perks"][:255],
                payload="batch:%s:%s" % (key, uid), provider_token=provider_token(), currency="INR",
                prices=[{"label": b["title"][:32], "amount": amt * 100}])


def create_razorpay_link(E, st, key, uid, name=""):
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
          {"inline_keyboard": [[{"text": ("💳 Pay %s now" % b["price"])[:64], "url": d["short_url"]}]]})
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


def _entitle(st, uid, key, **kw):
    users = st.setdefault("paid", {}).setdefault("users", {})
    u = users.setdefault(str(uid), {"batches": {}, "name": kw.get("name") or ""})
    if kw.get("name"):
        u["name"] = kw["name"]
    rec = u["batches"].setdefault(key, {})
    rec.update({k: v for k, v in kw.items() if k != "name"})
    return rec


_PAID_BOT_ID = {}


def paid_bot_id(E):
    """The paid-desk bot's own numeric id (cached). Falls back to the exam bot's id when
    PAID_BOT_TOKEN/PAID_TOKEN is not configured (ptg() itself falls back to E.tg in that case too)."""
    if "id" not in _PAID_BOT_ID:
        me = ptg(E, "getMe") or {}
        _PAID_BOT_ID["id"] = me.get("id") or E.bot_id()
    return _PAID_BOT_ID["id"]


def invite_ok(E, chat):
    """The paid-desk bot needs to be an administrator with the Invite Users right in the batch group."""
    m = ptg(E, "getChatMember", chat_id=str(chat), user_id=paid_bot_id(E)) or {}
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
        link = ptg(E, "createChatInviteLink", chat_id=b["chat"], member_limit=1,
                    expire_date=int(time.time()) + LINK_HOURS * 3600,
                    name=("%s-%s" % (key, str(uid)[-6:]))[:32])
    except Exception:
        link = None
    if not link:
        link = ptg(E, "createChatInviteLink", chat_id=b["chat"], member_limit=1,
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
    open_links = [(lid, r) for lid, r in ((st.get("paid") or {}).get("links") or {}).items()
                  if str(r.get("uid")) == str(uid) and r.get("status") not in ("paid", "expired", "cancelled")]
    if not got and not open_links:
        return _send(E, uid, t("dm_mybatches_none"))
    if open_links:
        lid, r = open_links[-1]
        _send(E, uid, "⏳ Pending payment for <b>%s</b> — %s" % (r.get("title"), r.get("short_url") or ""), None)
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
        if payload.startswith("paid_"):
            # returned from the Razorpay page: verify immediately (and DM the link if already paid)
            key = payload.replace("paid_", "")
            verify_payments(E, st, limit=25)
            return send_batch_detail(E, uid, key)
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
    ptg(E, "answerCallbackQuery", callback_query_id=cb.get("id"), text="")
    if data.startswith("batch:"):
        if is_private:
            send_batch_detail(E, uid, data.split(":", 1)[1])
        else:
            ptg(E, "answerCallbackQuery", callback_query_id=cb.get("id"), url=deep_link(E, "buy_" + data.split(":", 1)[1]))
        return
    if data.startswith("rzp:"):
        if is_private:
            create_razorpay_link(E, st, data.split(":", 1)[1], uid, name=name)
        else:
            ptg(E, "answerCallbackQuery", callback_query_id=cb.get("id"),
                 url=deep_link(E, "buy_" + data.split(":", 1)[1]))
        return
    if data.startswith("invoice:"):
        if is_private:
            send_invoice(E, uid, data.split(":", 1)[1])
        return
    if data.startswith("claim:"):
        # v11.4.12: manual claims are retired (admin order) — payment auto-unlocks access.
        key = data.split(":", 1)[1]
        b = batch(key)
        if not b:
            return
        _send(E, uid, "ℹ️ Ab claim karne ki zaroorat nahi — apna <b>personal payment link</b> se pay kijiye; \u23F3 payment verify hote hi join link <b>apne aap</b> isi chat me aa jayega.\n\nNaya link chahiye to batch ka <b>Pay &amp; Join</b> button dobara dabaiye.")
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
            ptg(E, "approveChatJoinRequest", chat_id=chat, user_id=int(uid))
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
    if WEBHOOK_MODE:
        E.log("desk: webhook live -> getUpdates skipped (spool drain answers students)")
        seen = set()
    while not WEBHOOK_MODE:
        if not E.FAKE and time.time() - started > budget_s:
            break
        r = ptg(E, "getUpdates", offset=off, timeout=1, allowed_updates=ALLOWED_UPDATES)
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
    pay = verify_payments(E, st)
    st = E.jload(force=True)
    st["desk"] = {"offset": off, "last": E.istnow().isoformat(timespec="seconds"),
                  "handled": int((st.get("desk") or {}).get("handled", 0)) + handled,
                  "payments": pay,
                  "seen": sorted(seen)[-200:]}
    E.jsave(st, "desk pass (%d handled, %s payments)" % (handled, pay))
    return {"handled": handled, "offset": off, "payments": pay}


def spool_drain(E, limit=80):
    """v11.4.13: consume updates that the Telegram webhook pushed into the spool file (web.py
    /ph route). Reuses the exact desk handlers, dedupes by update_id through the same seen-set,
    verifies payments right away so 'Pay & Join' feels instant. Single-flight flock: two drainers
    can never double-answer the same student."""
    import json as _json
    try:
        import fcntl as _fc
    except Exception:
        _fc = None
    lk = None
    if _fc:
        try:
            lk = os.open(SPOOL + ".lk", os.O_CREAT | os.O_RDWR, 0o600)
            _fc.flock(lk, _fc.LOCK_EX | _fc.LOCK_NB)
        except OSError:
            if lk is not None:
                os.close(lk)
            return {"skipped": "busy"}
    try:
        try:
            with open(SPOOL, "r", encoding="utf-8") as f:
                data = f.read()
        except FileNotFoundError:
            return {"drained": 0}
        lines = [x for x in data.splitlines() if x.strip()]
        if not lines:
            return {"drained": 0}
        take = lines[:limit]
        st = E.jload(force=True)
        seen = set(str(x) for x in ((st.get("desk") or {}).get("seen") or []))
        handled = 0
        for l in take:
            try:
                u = _json.loads(l)
            except Exception:
                continue
            uix = str(u.get("update_id", ""))
            if not uix or uix in seen:
                continue
            seen.add(uix)
            try:
                if u.get("message"):
                    handle_message(E, st, u["message"]); handled += 1
                elif u.get("callback_query"):
                    handle_callback(E, st, u["callback_query"]); handled += 1
                elif u.get("chat_join_request"):
                    handle_join_request(E, st, u["chat_join_request"]); handled += 1
            except Exception as e:
                E.log("webhook drain err:", str(e)[:140])
        pay = verify_payments(E, st)
        try:
            with open(SPOOL, "r", encoding="utf-8") as f:
                now = f.read().splitlines()
            keep = now[len(take):] if len(now) >= len(take) else []
            with open(SPOOL, "w", encoding="utf-8") as f:
                if keep:
                    f.write("\n".join(keep) + "\n")
        except Exception:
            pass
        st = E.jload(force=True)
        d = st.setdefault("desk", {})
        d["seen"] = sorted(seen | set(str(x) for x in (d.get("seen") or [])))[-200:]
        d["handled"] = int(d.get("handled", 0)) + handled
        d["webhook_last"] = E.istnow().isoformat(timespec="seconds")
        d["payments"] = pay
        E.jsave(st, "webhook drain (%d handled)" % handled)
        return {"drained": len(take), "handled": handled, "payments": pay}
    finally:
        if lk is not None:
            try:
                os.close(lk)
            except Exception:
                pass


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
