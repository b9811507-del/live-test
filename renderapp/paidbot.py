#!/usr/bin/env python3
"""paidbot — @Quizbotagri2_bot catalog + Razorpay + one-time join links.
Flow: /start or JOIN NOW -> catalog (batch, price, validity, attempts) -> batch card ->
👉 Pay ₹X & Join -> Razorpay HOSTED payment link -> webhook capture -> one-time invite link DM (MT bridge).
DEMO_MODE=1: fake payment page (end-to-end visible without keys).
"""
import os, json, time, sqlite3, threading, urllib.request, urllib.parse, html

TOKEN = os.environ.get("PAID_BOT_TOKEN", "8533597307:AAF_8uqRRxlQ0dKQQm5-o9KEkUHrNqZKp0c")
RZP_ID = os.environ.get("RZP_KEY_ID", "")
RZP_SECRET = os.environ.get("RZP_KEY_SECRET", "")
RZP_WEBHOOK_SECRET = os.environ.get("RZP_WEBHOOK_SECRET", "")
MT_URL = os.environ.get("MT_URL", "")            # telethon bridge: /genlink?chat=&name= -> {link}
PUB = os.environ.get("PUBLIC_URL", "").rstrip("/")   # our base URL (for webhook note + demo pay page)
DEMO = os.environ.get("DEMO_MODE") == "1"
DB = os.environ.get("DATA_PATH", os.path.join(os.path.dirname(__file__), "paid.db"))

BATCHES = {
    "afo":       {"title": "🌆 AFO MAINS BATCH 2026", "price": 199, "chat": "-1003687531473",
                  "what": "Complete AFO mains course · daily 50-Q live tests · full PDFs"},
    "nemraj":    {"title": "📚 NEMRAJ SUNDA BOOK BATCH", "price": 99, "chat": "",
                  "what": "Nemraj MCQ 2026 full book series · 3108 Q · revisions"},
    "iari":      {"title": "🌱 IARI BOOK MCQ 2026 BATCH", "price": 99, "chat": "-1003922097468",
                  "what": "IARI book complete sequence · 7448 Q · PDF library"},
    "malwa":     {"title": "🚜 MALWA COMPLETE (VOL 1 + VOL 2 + HORTICULTURE)", "price": 151, "chat": "-1003761821341",
                  "what": "Saare 3 Malwa books ka structured batch + test series"},
    "rk":        {"title": "🧪 RK SHARMA AGRI SERIES", "price": 99, "chat": "-1003880198347",
                  "what": "RK Sharma full MCQ series + model papers"},
    "sugarcane": {"title": "🎋 SUGARCANE PREMIUM BATCH", "price": 151, "chat": "-1003707610763",
                  "what": "Sugarcane special course + current affairs + tests"},
    "pashudhan": {"title": "🐄 PASHUDHAN ADHIKARI BATCH", "price": 151, "chat": "-10033947957354",
                  "what": "Pashudhan Adhikari full syllabus batch + MCQs"},
}
VALID = "🗓 Validity: <b>Lifetime</b>  ·  🔁 Attempts: <b>Unlimited</b>"

def db():
    c = sqlite3.connect(DB, timeout=6)
    c.execute("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INT, batch TEXT,"
              " link TEXT, status TEXT, note TEXT, ts REAL, UNIQUE(uid,batch,status))")
    c.execute("CREATE INDEX IF NOT EXISTS ix ON orders(link)")
    return c

def tg(m, **kw):
    for a in range(5):
        try:
            rq = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{m}",
                data=json.dumps({k: v for k, v in kw.items() if v is not None}).encode(),
                headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(rq, timeout=30).read())
            if r.get("ok"):
                return r["result"]
            if r.get("error_code") == 429:
                time.sleep(r.get("parameters", {}).get("retry_after", 3) + 1); continue
            return {"_err": r.get("description")}
        except Exception:
            time.sleep(2 + 2 * a)
    return {"_err": "retries"}

def api_post(path, body, auth=True):
    hdr = {"Content-Type": "application/json"}
    if auth and RZP_ID:
        import base64
        hdr["Authorization"] = "Basic " + base64.b64encode(f"{RZP_ID}:{RZP_SECRET}".encode()).decode()
    rq = urllib.request.Request(f"https://api.razorpay.com/v1{path}", data=json.dumps(body).encode(), headers=hdr)
    return json.loads(urllib.request.urlopen(rq, timeout=30).read())

# ---------------- messages ----------------
def catalog_msg():
    L = ["🎓 <b>PAID BATCHES — AGRI LEARNING POINT</b>", "🖊 By <b>SatyamSir</b>", "",
         "Lifetime validity · Unlimited attempts · Daily live tests included 👇", ""]
    L.append("— Tap a batch for details &amp; price —")
    return "\n".join(L)

def catalog_kb():
    rows = [[{"text": f"{b['title'].split(' ')[0]} {b['title'].split(' ',1)[1][:34]} — ₹{b['price']}", "callback_data": f"b:{k}"}]
            for k, b in BATCHES.items()]
    return {"inline_keyboard": rows}

def batch_msg(k):
    b = BATCHES[k]
    return (f"{b['title']}\n\n💰 <b>₹{b['price']}</b>  (one-time)\n{VALID}\n\n📦 {b['what']}\n\n"
            "✅ Payment ke turant baad <b>one-time join link</b> — sirf AAP join kar sakte ho 👇")

def batch_kb(k):
    pay = {"text": f"👉 Pay ₹{BATCHES[k]['price']} & Join", "callback_data": f"p:{k}"}
    if k == "afo":
        pay["text"] = f"💳 Pay & Join ₹{BATCHES[k]['price']}"
    return {"inline_keyboard": [[pay], [{"text": "◀ All batches", "callback_data": "cat"}]]}

# ---------------- payment ----------------
def make_pay_link(uid, batch):
    b = BATCHES[batch]
    note = f"{uid}:{batch}:{int(time.time())}"
    with db() as c:
        pend = c.execute("SELECT id,link,status FROM orders WHERE uid=? AND batch=? AND status='created'", (uid, batch)).fetchone()
        if pend:
            return pend[1]
    if DEMO or not RZP_ID:
        link = f"{PUB}/paydemo/{note}" if PUB else f"(demo) {b['title']} ₹{b['price']}"
        with db() as c:
            c.execute("INSERT INTO orders(uid,batch,link,status,note,ts) VALUES(?,?,?,?,?,?)",
                      (uid, batch, link, "created", note, time.time()))
        return link
    try:
        r = api_post("/payment/link", {"amount": b["price"] * 100, "currency": "INR",
                "customer": {"name": f"user{uid}"}, "notify": {"email": False, "sms": False},
                "reference_id": note, "description": b["title"], "reminder_contact": 0,
                "callback_url": f"{PUB}/done?n={note}"})
        link = r.get("short_url")
        with db() as c:
            c.execute("INSERT INTO orders(uid,batch,link,status,note,ts) VALUES(?,?,?,?,?,?)",
                      (uid, batch, link, "created", note, time.time()))
        return link
    except Exception as e:
        return None

def gen_onetime_link(chat_id, tag):
    if MT_URL:
        try:
            r = json.loads(urllib.request.urlopen(f"{MT_URL}/genlink?chat={chat_id}&name={urllib.parse.quote(tag)}&member_limit=1", timeout=25).read())
            return r.get("link")
        except Exception:
            return None
    return None

def fulfill(uid, batch, note, paid=True):
    b = BATCHES[batch]
    with db() as c:
        c.execute("UPDATE orders SET status=?, ts=? WHERE note=?", ("paid" if paid else "failed", time.time(), note))
        done = c.execute("SELECT COUNT(*) FROM orders WHERE uid=? AND batch=? AND status='paid'", (uid, batch)).fetchone()[0]
    if paid and done == 1:
        link = gen_onetime_link(b["chat"], f"pay:{note}")
        ok = b.get("chat") and link
        if ok:
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text=(
                f"✅ <b>Payment successful — {b['title']}</b>\n\n🎟 <b>One-time join link</b> (sirf 1 member join kar sakta hai — sirf aap):\n{link}\n\n"
                f"⚠️ Ye link share mat karna — ek hi use allowed hai. Join ke baad pinned Intro padh lena 📌"))
        else:
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text=(
                f"✅ <b>Payment successful — {b['title']}</b>\n\n⏳ Join link admin ke setup se deliver hoga "
                f"({'one-time link service pending: session-API' if not MT_URL else 'group-add pending'})\n"
                f"📌 Admin ko ye dikhao — turant add kar denge: <b>{b['title']}</b> · txn <code>{note}</code>"))
    elif paid:
        tg("sendMessage", chat_id=uid, parse_mode="HTML", text=f"ℹ️ Aap already <b>{b['title']}</b> me ho (lifetime). Koi extra charge nahi.")

# ---------------- webhook / demo callback ----------------
def handle_webhook(body):
    try:
        import hmac, hashlib
        sig = body.get("_sig", "")
        raw = json.dumps({k: v for k, v in body.items() if k != "_sig"}, separators=(",", ":"))
        if RZP_WEBHOOK_SECRET and not hmac.compare_digest(sig, hmac.new(RZP_WEBHOOK_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()):
            return False
        ev = body.get("event", "")
        payload = (body.get("payload") or {})
        pl = payload.get("payment_link") or {}
        note = pl.get("reference_id") or (payload.get("payment", {}) or {}).get("notes", {}).get("ref", "")
        if ev in ("payment_link.captured", "payment.captured") and ":" in note:
            uid, batch = int(note.split(":")[0]), note.split(":")[1]
            fulfill(uid, batch, note)
        elif ev in ("payment_link.expired", "payment.failed") and ":" in note:
            uid, batch = int(note.split(":")[0]), note.split(":")[1]
            fulfill(uid, batch, note, paid=False)
    except Exception as e:
        print("webhook err", e)
    return True

def demo_page(note):
    uid, batch = int(note.split(":")[0]), note.split(":")[1]
    b = BATCHES[batch]
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<body style='font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1621;color:#e9eef5;"
            f"display:flex;min-height:92vh;align-items:center;justify-content:center;margin:0'><div style='text-align:center;max-width:420px;padding:20px'>"
            f"<div style='font-size:40px'>💳</div><h2>Pay ₹{b['price']} — {html.escape(b['title'])}</h2>"
            f"<p style='color:#8fa1b8'>DEMO payment page (Razorpay keys lagne par yahan real Razorpay checkout khulega)</p>"
            f"<a href='{PUB}/demopay?n={note}' style='display:inline-block;background:#8774e2;color:#fff;padding:13px 26px;border-radius:12px;font-weight:700;text-decoration:none'>✅ Pay ₹{b['price']} (simulate)</a>"
            f"</div></body>")

# ---------------- main poll loop ----------------
OFF = 0
def run(offset=None):
    global OFF
    if offset:
        OFF = offset
    while True:
        try:
            r = urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={OFF}&timeout=40&allowed_updates=[\"message\",\"callback_query\"]", timeout=55)
            for u in json.loads(r.read()).get("result", []):
                OFF = u["update_id"] + 1
                handle(u)
        except Exception:
            time.sleep(3)

def handle(u):
    if "message" in u:
        m = u["message"]
        txt = (m.get("text") or "").lower().strip()
        uid = m["chat"]["id"]
        if txt.startswith("/start"):
            cb = txt.split(" ")[1] if " " in txt else ""
            if cb.startswith("batch"):
                tg("sendMessage", chat_id=uid, parse_mode="HTML", text=catalog_msg(), reply_markup=catalog_kb()); return
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text=(
                "🌾 <b>AGRI LEARNING POINT</b> — SatyamSir\n\n🎓 Paid batches + daily LIVE tests ka official bot.\n"
                " Neeche batch chuno:"), reply_markup=catalog_kb())
        elif txt in ("/help",):
            tg("sendMessage", chat_id=uid, text="Commands: /start · /batches · /status")
        elif txt in ("/status", "/my"):
            with db() as c:
                rows = c.execute("SELECT batch,status,ts FROM orders WHERE uid=? ORDER BY id DESC LIMIT 8", (uid,)).fetchall()
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text="📋 <b>Aapke orders</b>\n" +
               ("\n".join(f"• {BATCHES.get(r[0],{}).get('title',r[0])} — {r[1]}" for r in rows) or "Abhi koi order nahi."))
        elif txt.startswith("/batches"):
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text=catalog_msg(), reply_markup=catalog_kb())
    if "callback_query" in u:
        q = u["callback_query"]
        uid = q["from"]["id"]
        data = q.get("data", "")
        if data == "cat":
            tg("editMessageText", chat_id=q["message"]["chat"]["id"], message_id=q["message"]["message_id"],
               parse_mode="HTML", text=catalog_msg(), reply_markup=catalog_kb())
        elif data.startswith("b:"):
            k = data[2:]
            tg("editMessageText", chat_id=q["message"]["chat"]["id"], message_id=q["message"]["message_id"],
               parse_mode="HTML", text=batch_msg(k), reply_markup=batch_kb(k))
        elif data.startswith("p:"):
            k = data[2:]
            link = make_pay_link(uid, k)
            if link and link.startswith("http"):
                tg("answerCallbackQuery", callback_query_id=q["id"], text="Opening secure payment…")
                tg("sendMessage", chat_id=uid, parse_mode="HTML",
                   text=f"🔐 <b>Secure payment</b> — ₹{BATCHES[k]['price']} (Razorpay):\n{link}\n\n"
                        f"Pay karte hi <b>one-time join link</b> auto mil jayega ✅")
            else:
                tg("answerCallbackQuery", callback_query_id=q["id"], text="Payment setup pending (keys)", show_alert=True)

if __name__ == "__main__":
    run()
