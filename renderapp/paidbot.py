#!/usr/bin/env python3
"""paidbot — @Quizbotagri2_bot catalog + Razorpay + one-time join links + ADMIN AI control.
Public flow: /start -> catalog (batch, price, lifetime, unlimited attempts) -> batch card ->
👉 Pay -> Razorpay Orders + hosted checkout -> HMAC /confirm (webhook/poll backstops) -> one-time invite link DM.
ADMIN (id 1138783169) only: AI chat in plain Hinglish/English — "AFO batch 299 kar do",
"add batch: <naam> ₹<price> <group-id>" — + panel buttons (➕ Add / 💰 Fees / 🗑 Remove / 📊 Today / 🔄 Sync).
Batches persist: sqlite + state/batches.json pushed to GitHub (survives Render redeploys).
Non-admin free text: NO reply to them — silently forwarded to admin DM (buyer txn msgs get 🔔).
DEMO_MODE=1: fake payment page. MT bridge (MT_URL) for member_limit=1 links when available.
"""
import os, sys, json, time, sqlite3, threading, re, base64, socket
import urllib.request, urllib.parse, html as _html

# --- force IPv4 for all urllib calls (Render oregon IPv6 to TG/RZP can blackhole) ---
_gai = socket.getaddrinfo
def _gai4(host, port, family=0, type=0, proto=0, flags=0):
    try:
        res = [r for r in _gai(host, port, socket.AF_INET, type, proto, flags) if r[0] == socket.AF_INET]
        if res:
            return res
    except Exception:
        pass
    return _gai(host, port, family, type, proto, flags)
socket.getaddrinfo = _gai4

try:
    import llmsupport
except ImportError:  # when imported as renderapp.paidbot from repo root (agents/tests)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import llmsupport

TOKEN = os.environ.get("PAID_BOT_TOKEN", "8533597307:AAF_8uqRRxlQ0dKQQm5-o9KEkUHrNqZKp0c")
RZP_ID = os.environ.get("RZP_KEY_ID", "")
RZP_SECRET = os.environ.get("RZP_KEY_SECRET", "")
RZP_WEBHOOK_SECRET = os.environ.get("RZP_WEBHOOK_SECRET", "")
MT_URL = os.environ.get("MT_URL", "")
PUB = (os.environ.get("PUBLIC_URL", "") or "https://livescore-zp5w.onrender.com").rstrip("/").rstrip("/")
DEMO = os.environ.get("DEMO_MODE") == "1"
DB = os.environ.get("DATA_PATH", os.path.join(os.path.dirname(__file__), "paid.db"))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1138783169"))
GH_TOKEN = os.environ.get("GH_PUSH_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPO", "b9811507-del/live-test")
BATCH_FILE = "state/batches.json"

# seed batches (used only if DB empty AND GitHub file missing)
BATCHES_SEED = {
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

def db():
    c = sqlite3.connect(DB, timeout=6)
    c.execute("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INT, batch TEXT,"
              " link TEXT, status TEXT, note TEXT, ts REAL, UNIQUE(uid,batch,status))")
    c.execute("CREATE INDEX IF NOT EXISTS ix ON orders(link)")
    c.execute("CREATE TABLE IF NOT EXISTS batches(key TEXT PRIMARY KEY, title TEXT, price INT, chat TEXT, what TEXT, updated REAL)")
    return c

def tg(m, **kw):
    for a in range(3):
        try:
            rq = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{m}",
                data=json.dumps({k: v for k, v in kw.items() if v is not None}).encode(),
                headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(rq, timeout=15).read())
            if r.get("ok"):
                return r["result"]
            if r.get("error_code") == 429:
                time.sleep(min(r.get("parameters", {}).get("retry_after", 3), 5)); continue
            return {"_err": r.get("description")}
        except Exception:
            time.sleep(0.6 + a)
    return {"_err": "retries"}

# ---------------- dynamic batches (DB + GitHub persistence) ----------------
_bcache = {"t": 0.0, "d": None}

def get_batches():
    if _bcache["d"] is not None and time.time() - _bcache["t"] < 25:
        return _bcache["d"]
    out = {}
    with db() as c:
        for k, title, price, chat, what in c.execute("SELECT key,title,price,chat,what FROM batches"):
            out[k] = {"title": title, "price": price, "chat": chat, "what": what}
    if not out:
        out = {k: dict(v) for k, v in BATCHES_SEED.items()}
        with db() as c:
            for k, b in out.items():
                c.execute("INSERT OR REPLACE INTO batches VALUES(?,?,?,?,?,?)",
                          (k, b["title"], b["price"], b["chat"], b["what"], time.time()))
    _bcache.update(t=time.time(), d=out)
    return out

def _save(out, push=True):
    with db() as c:
        c.execute("DELETE FROM batches")
        for k, b in out.items():
            c.execute("INSERT OR REPLACE INTO batches VALUES(?,?,?,?,?,?)",
                      (k, b["title"], b["price"], b.get("chat", ""), b.get("what", ""), time.time()))
    _bcache.update(t=time.time(), d=out)
    if push:
        push_github(out)

def put_batch(key, title, price, chat="", what=""):
    out = dict(get_batches())
    out[key] = {"title": title, "price": int(price), "chat": chat or "", "what": what or "Full course + daily live tests + PDFs"}
    _save(out); return out[key]

def del_batch(key):
    out = dict(get_batches())
    if key not in out:
        return None
    b = out.pop(key); _save(out); return b

def push_github(out):
    if not GH_TOKEN:
        return False
    try:
        body = {"message": f"[paidbot] batches update {time.strftime('%H:%M UTC')}",
                "content": base64.b64encode(json.dumps(out, ensure_ascii=False, indent=1).encode()).decode()}
        try:
            cur = _gh("GET", f"/repos/{GH_REPO}/contents/{BATCH_FILE}")
            body["sha"] = cur["sha"]
        except Exception:
            pass
        _gh("PUT", f"/repos/{GH_REPO}/contents/{BATCH_FILE}", body)
        return True
    except Exception as e:
        print("batches push fail:", e); return False

def pull_github():
    """On boot: if repo has batches.json, trust it (source of truth across redeploys)."""
    try:
        raw = urllib.request.urlopen(f"https://raw.githubusercontent.com/{GH_REPO}/main/{BATCH_FILE}", timeout=20).read()
        out = json.loads(raw)
        if isinstance(out, dict) and out:
            norm = {k: {"title": b.get("title", k), "price": int(b.get("price", 0)),
                        "chat": b.get("chat", ""), "what": b.get("what", "")} for k, b in out.items()}
            cur = _bcache["d"] if _bcache["d"] else get_batches()
            if cur != norm:
                _save(norm, push=False)
            return len(norm)
    except Exception:
        pass
    return 0

def _gh(method, path, body=None):
    rq = urllib.request.Request(f"https://api.github.com{path}",
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {GH_TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json", "User-Agent": "paidbot"})
    return json.loads(urllib.request.urlopen(rq, timeout=30).read() or b"{}")

# ---------------- messages ----------------
def catalog_msg():
    return ("🎓 <b>PAID BATCHES — AGRI LEARNING POINT</b>\n\n"
            "💳 <b>Ek baar lo · Lifetime access · Koi expiry nahi</b>\n\n"
            "🖊 <b>By SatyamSir</b>\n\n"
            "⬇️ <b>Tap a batch — details &amp; secure payment</b>\n"
            "⬇️ <b>बैच पर टैप करें — पूरी जानकारी व सुरक्षित पेमेंट</b>")

def catalog_kb(uid=None):
    rows = []
    for k, b in get_batches().items():
        em, rest = b["title"].split(" ", 1)
        rows.append([{"text": f"{em} {rest[:30]} — ₹{b['price']}\n🗓 Lifetime  ·  🔁 Unlimited Attempts",
                      "callback_data": f"b:{k}"}])
    if uid == ADMIN_ID:
        rows.append([{"text": "🛠 Admin Panel — batches & fees", "callback_data": "ad:panel"}])
    return {"inline_keyboard": rows}

def batch_msg(k):
    b = get_batches()[k]
    return (f"{_html.escape(b['title'])}\n\n"
            f"💰 <b>Fees: ₹{b['price']}</b> (one-time)\n\n"
            f"🗓 <b>Validity: Lifetime</b> · <b>आयुभर</b>\n\n"
            f"🔁 <b>Attempts: Unlimited</b> · <b>असीमित प्रयास</b>\n\n"
            f"📦 {_html.escape(b['what'])}\n\n"
            "🔑 Payment ke turant baad <b>One-Time Join Link</b>\n"
            "🔑 पेमेंट के तुरंत बाद <b>व्यक्तिगत जॉइन लिंक</b> — सिर्फ़ आप join कर सकेंगे")

def batch_kb(k):
    pay = {"text": f"👉 Pay ₹{get_batches()[k]['price']} & Join", "callback_data": f"p:{k}"}
    if k == "afo":
        pay["text"] = f"💳 Pay & Join ₹{get_batches()[k]['price']}"
    return {"inline_keyboard": [[pay], [{"text": "◀ All batches", "callback_data": "cat"}]]}

# ---------------- admin panel ----------------
def panel_kb():
    return {"inline_keyboard": [
        [{"text": "➕ Add Batch", "callback_data": "ad:add"}, {"text": "💰 Change Fees", "callback_data": "ad:price"}],
        [{"text": "🗑 Remove Batch", "callback_data": "ad:rem"}, {"text": "📊 Today's Orders", "callback_data": "ad:today"}],
        [{"text": "🔄 Pull from GitHub", "callback_data": "ad:pull"}, {"text": "📦 Push to GitHub", "callback_data": "ad:push"}],
        [{"text": "◀ Catalog", "callback_data": "cat"}]]}

def remove_kb():
    return {"inline_keyboard": [[{"text": f"🗑 {b['title'][:36]}", "callback_data": f"ad:rm:{k}"}] for k, b in get_batches().items()]
                            + [[{"text": "⬅️ Panel", "callback_data": "ad:panel"}]]}

WAIT = {}   # uid -> "add" | "price"

SYS = ("You control a Telegram paid-batch bot for an agri-education admin. "
       "Current batches JSON: {BATCHES} "
       "Reply ONLY with one JSON object, no prose, no code fence: "
       '{{"reply": "<short Hinglish confirmation, plain text>", '
       '"action": "none|add_batch|set_price|remove_batch|list", "args": {{...}} }}. '
       "RULES: set_price.price MUST be the NEW ABSOLUTE rupee value. If user says increase/decrease by X (badhao/ghatao/+X/-X/50 rupya zyada), "
       "compute current_price +/− X yourself (e.g. AFO 199 + \"50 badha do\" -> price 249). "
       "add_batch.args: key=short english slug from name only; title=batch name only (NO verbs like add/karo/batch banao, emoji prefix allowed); "
       "price=int; chat=-100xxxxxxxxxx or t.me link or \"\"; what=one line about content or \"\". "
       "remove/list take args {{key}} / {{}}. Questions like 'kaunse batches hain' -> action=list. "
       "Never invent batch keys; match closest existing. General question -> action=none with helpful reply.")

def admin_ai(text):
    B = get_batches()
    out = llmsupport.ask(SYS.replace("{BATCHES}", json.dumps(B, ensure_ascii=False)), text, 1500)
    j = llmsupport.try_json(out) if out else None
    if not j:
        j = _regex_parse(text, B)
    if not j:
        return "⚠️ Samajh nahi aaya. Example:\n<code>AFO ki fees 299 kar do</code>\n<code>add batch: Soil Health ₹149 -1003761821341</code>"
    act, args, reply = j.get("action", "none"), j.get("args") or {}, _html.escape(str(j.get("reply") or ""))
    try:
        if act == "add_batch" and args.get("title"):
            key = re.sub(r"[^a-z0-9]+", "", str(args.get("key") or args["title"]).lower())[:14] or f"b{int(time.time())%9999}"
            b = put_batch(key, str(args["title"])[:70], int(args.get("price") or 99), str(args.get("chat") or ""), str(args.get("what") or ""))
            return f"✅ <b>Batch added</b> → <code>{key}</code>\n{b['title'][:60]} — ₹{b['price']} · Lifetime · Unlimited\n📤 GitHub save: {'ok' if GH_TOKEN else 'no token (DB only)'}"
        if act == "set_price" and args.get("key"):
            B2 = dict(get_batches())
            if args["key"] in B2:
                old = B2[args["key"]]["price"]
                B2[args["key"]]["price"] = int(args.get("price") or old)
                _save(B2)
                return (f"✅ <b>{B2[args['key']]['title'][:44]}</b> ki fees ab <b>₹{B2[args['key']]['price']}</b> "
                        f"(pehle ₹{old} thi) — catalog update ho gaya. Galat hua ho to bata do, wapas kar dunga.")
            return f"⚠️ Batch key <code>{_html.escape(str(args['key']))}</code> nahi mila. /panel me list hai."
        if act == "remove_batch" and args.get("key"):
            b = del_batch(args["key"])
            return f"🗑 Removed: <b>{_html.escape(b['title'])}</b>" if b else "⚠️ Wo batch mila hi nahi."
        if act == "list":
            return "📦 <b>Batches:</b>\n" + "\n".join(f"• <code>{k}</code> — {v['title'][:46]} · ₹{v['price']}" for k, v in get_batches().items())
    except Exception as e:
        return f"⚠️ Action fail: {e}"
    return reply or "👍"

GENERIC = {"batch", "book", "full", "complete", "series", "premium", "special", "2026", "sunda", "horticulture", "vol", "pashudhan"}
def _match_batch(t, B):
    """best-scoring batch for text: exact key 10 pts, distinctive title words by length."""
    best, bs = None, 0
    for k, b in B.items():
        sc = 10 if re.search(rf"\b{re.escape(k)}\b", t) else 0
        for w in re.sub(r"[^a-z0-9 ]", " ", b["title"].lower()).split():
            if len(w) > 3 and w not in GENERIC and w in t:
                sc = max(sc, len(w) + 3)
        if sc > bs:
            best, bs = k, sc
    return best if bs else None

def _regex_parse(text, B):
    t = text.lower().strip()
    if re.search(r"(?:add|naya|new)\s+(?:a\s+)?batch", t) or ("₹" in text and re.search(r"(?:\d+)", t) and not _match_batch(t, B)):
        m = re.search(r"(?:₹|rs\.?\s*|price[:\s]*|fees?[:\s]*)(\d+)", t)
        chat = re.search(r"(-100\d{8,11}|t\.me/[\w/+]+)", text)
        seg = re.sub(r"(?i)(?:please\s+)?(add|new|naya)\s*(?:a\s+)?batch[:\s]*", "", text).strip()
        seg = re.sub(r"(?i)\s*(?:₹\s*\d+|rs\.?\s*\d+|price[:\s]+\d+|fees?[:\s]+\d+).*$", "", seg)
        seg = re.sub(r"(?i)\s*group[:\s]*(-100\d{8,11}|t\.me/\S+)\s*$", "", seg).strip(" -:,.")
        key = re.sub(r"[^a-z0-9]+", "", seg.lower())[:14] or f"b{int(time.time()) % 9999}"
        return {"reply": "", "action": "add_batch", "args": {"key": key, "title": seg[:70],
                "price": int(m.group(1)) if m else 99, "chat": chat.group(1) if chat else "", "what": ""}}
    k = _match_batch(t, B)
    if k:
        m3 = re.search(r"(?:₹|rs\.?\s*|price|fees?|cost)\D{0,8}?(\d{2,6})", t)
        if re.search(r"remove|delete|hata", t):
            return {"reply": "", "action": "remove_batch", "args": {"key": k}}
        if m3:
            return {"reply": "", "action": "set_price", "args": {"key": k, "price": int(m3.group(1))}}
        return {"reply": "", "action": "list"} if re.search(r"list|kaun|console|batao|status", t) else None
    return None

def admin_orders_today():
    day0 = time.time() - (time.time() % 86400) - 19800
    with db() as c:
        rows = c.execute("SELECT batch,status,COUNT(*),SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) FROM orders"
                         " WHERE ts>=? GROUP BY batch,status ORDER BY ts DESC", (day0,)).fetchall()
        tot = c.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END),0) FROM orders WHERE ts>=?", (day0,)).fetchone()
    B = get_batches()
    lines = "\n".join(f"• {_html.escape(B.get(r[0],{}).get('title', r[0])[:34])} — {r[2]} {r[1]}" for r in rows) or "Aaj koi order nahi."
    coll = sum(B.get(r[0], {}).get("price", 0) * r[3] for r in rows if r[1] == "paid")
    return f"📊 <b>Today ({time.strftime('%d %b')})</b>\n{lines}\n\n💰 Paid: <b>{tot[1]}</b> · orders: {tot[0]}\n🧾 Collected: <b>~₹{coll}</b>"

# ---------------- payment (Razorpay Orders + Checkout) ----------------
def _rzp_auth():
    return "Basic " + base64.b64encode(f"{RZP_ID}:{RZP_SECRET}".encode()).decode()

_last_alert = [0.0]
def _admin_alert(msg):
    """DM admin on payment problems (throttled 3 min). Never raises."""
    try:
        if time.time() - _last_alert[0] < 180:
            return
        _last_alert[0] = time.time()
        tg("sendMessage", chat_id=ADMIN_ID, text=f"🚨 PAYMENT ISSUE: {msg}")
    except Exception as e:
        print("admin alert fail:", e)

def api_post(path, body, auth=True, retries=2):
    """POST to Razorpay with retry on transient errors (timeout/429/5xx). 4xx fails fast."""
    import urllib.error as UERR
    hdr = {"Content-Type": "application/json"}
    if auth and RZP_ID:
        hdr["Authorization"] = _rzp_auth()
    last = None
    for i in range(retries + 1):
        try:
            rq = urllib.request.Request(f"https://api.razorpay.com/v1{path}", data=json.dumps(body).encode(), headers=hdr)
            return json.loads(urllib.request.urlopen(rq, timeout=30).read())
        except UERR.HTTPError as e:
            last = e
            if e.code < 500 and e.code != 429:
                break                      # auth/bad-request — retrying is useless
        except Exception as e:
            last = e
        if i < retries:
            time.sleep([2, 5][i])
    raise RuntimeError(f"razorpay post {path} failed after retries: {last}")

def _rzp_get(path):
    rq = urllib.request.Request(f"https://api.razorpay.com/v1{path}", headers={"Authorization": _rzp_auth()})
    return json.loads(urllib.request.urlopen(rq, timeout=25).read())

def _tok(note):
    import hmac, hashlib
    return hmac.new((RZP_SECRET or "demo").encode(), note.encode(), hashlib.sha256).hexdigest()[:16]

def verify_sig(oid, pid, sig):
    import hmac, hashlib
    return hmac.compare_digest(hmac.new(RZP_SECRET.encode(), f"{oid}|{pid}".encode(), hashlib.sha256).hexdigest(), sig or "")

def make_order_local(uid, batch):
    """DB-only reservation — NO network. Instant, so the bot never blocks."""
    b = get_batches().get(batch)
    if not b:
        return None
    with db() as c:
        pend = c.execute("SELECT id,note,link,ts FROM orders WHERE uid=? AND batch=? AND status='created' ORDER BY id DESC LIMIT 1", (uid, batch)).fetchone()
    if pend and time.time() - float(pend[3] or 0) > 13 * 60:
        with db() as c:   # Razorpay orders expire in 15 min — stop reusing a stale one
            c.execute("UPDATE orders SET status='expired' WHERE id=?", (pend[0],))
        pend = None
    if pend:
        return {"demo": DEMO or not RZP_ID, "note": pend[1], "amount": b["price"]}
    note = f"{uid}:{batch}:{int(time.time())}"
    with db() as c:
        c.execute("INSERT INTO orders(uid,batch,link,status,note,ts) VALUES(?,?,?,?,?,?)", (uid, batch, "", "created", note, time.time()))
    return {"demo": DEMO or not RZP_ID, "note": note, "amount": b["price"]}

def ensure_rzp_order(note):
    """Create the Razorpay order lazily (called from the web request thread, never the bot loop)."""
    with db() as c:
        row = c.execute("SELECT batch,link,status FROM orders WHERE note=?", (note,)).fetchone()
    if not row:
        raise RuntimeError("order not found")
    if row[1] and row[1].startswith("order_"):
        return row[1]
    if row[2] not in ("created",):
        raise RuntimeError("order closed — start again")
    price = get_batches().get(row[0], {}).get("price")
    if price is None:
        raise RuntimeError("batch removed")
    try:
        r = api_post("/orders", {"amount": int(price) * 100, "currency": "INR",
                                 "receipt": note, "notes": {"ref": note},
                                 "partial_enabled": False})
        with db() as c:
            c.execute("UPDATE orders SET link=? WHERE note=?", (r["id"], note))
        return r["id"]
    except Exception as e:
        _admin_alert(f"order create fail note={note}: {str(e)[:160]}")
        raise

def make_pay_link(uid, batch):
    o = make_order_local(uid, batch)
    if not o:
        return None
    if o["demo"]:
        return f"{PUB}/paydemo/{o['note']}"
    return f"{PUB}/p/{o['note']}/{_tok(o['note'])}"

def join_link(batch):
    return os.environ.get(f"JOIN_{batch.upper()}", "")

def gen_onetime_link(chat_id, tag):
    if MT_URL:
        try:
            r = json.loads(urllib.request.urlopen(f"{MT_URL}/genlink?chat={chat_id}&name={urllib.parse.quote(tag)}&member_limit=1", timeout=25).read())
            return r.get("link")
        except Exception:
            return None
    return None

def fulfill(uid, batch, note, paid=True):
    b = get_batches().get(batch, {})
    with db() as c:
        c.execute("UPDATE orders SET status=?, ts=? WHERE note=?", ("paid" if paid else "failed", time.time(), note))
        done = c.execute("SELECT COUNT(*) FROM orders WHERE uid=? AND batch=? AND status='paid'", (uid, batch)).fetchone()[0]
    title = b.get("title", batch)
    if paid and done == 1:
        link = gen_onetime_link(b.get("chat", ""), f"pay:{note}")
        ok = b.get("chat") and link
        if ok:
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text=(
                f"✅ <b>Payment successful — {_html.escape(title)}</b>\n\n🎟 <b>One-time join link</b> (sirf 1 member join kar sakta hai — sirf aap):\n{link}\n\n"
                f"⚠️ Ye link share mat karna — ek hi use allowed hai. Join ke baad pinned Intro padh lena 📌"))
        else:
            jl = join_link(batch)
            extra = (f"\n\n🎟 <a href=\"{jl}\">👉 Tap to Join (Request bhejo — turant approve ho jaayega)</a>"
                     if jl else "\n\n⏳ Group me join request bhejo — paid list se turant approve ho jaayega.")
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text=(
                f"✅ <b>Payment successful — {_html.escape(title)}</b>" + extra +
                f"\n🧾 Order ref: <code>{note}</code>"))
        tg("sendMessage", chat_id=ADMIN_ID, parse_mode="HTML", text=(
            f"💰 <b>PAID</b> — {_html.escape(title)}\n👤 <code>{uid}</code> · txn <code>{note}</code>" + (f"\n🎟 link sent ✓" if ok else "\n⚠️ link pending — /give " + note)))
    elif paid:
        tg("sendMessage", chat_id=uid, parse_mode="HTML", text=f"ℹ️ Aap already <b>{_html.escape(title)}</b> me ho (lifetime). Koi extra charge nahi.")

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

def checkout_page(note, tok=""):
    uid, batch = int(note.split(":")[0]), note.split(":")[1]
    b = get_batches().get(batch) or {"title": "AGRI Batch", "price": 0}
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Pay ₹{b['price']} — {_html.escape(b['title'])}</title>
<style>body{{font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1621;color:#e9eef5;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.c{{background:#182333;border-radius:16px;padding:26px;max-width:400px;width:92%;box-shadow:0 20px 60px -20px #000}}
h2{{margin:0 0 4px;font-size:18px}}.p{{color:#8fa1b8;font-size:13.5px;margin:0 0 18px}}
button{{width:100%;padding:15px;border:0;border-radius:12px;background:#3395ff;color:#fff;font-size:16px;font-weight:700;cursor:pointer}}
button:disabled{{opacity:.6}}.f{{margin-top:14px;font-size:11.5px;color:#8fa1b8;text-align:center}}</style></head><body>
<div class=c><div style="font-size:34px;text-align:center">🌾</div>
<h2 style="text-align:center">{_html.escape(b['title'])}</h2>
<p class=p style="text-align:center">₹{b['price']} one-time · Lifetime · Unlimited attempts<br>पेमेंट Razorpay पर सुरक्षित · <b>By SatyamSir</b></p>
<button id=pay>💳 Pay ₹{b['price']} via Razorpay</button>
<div class=f>Payment होते ही Join link Telegram पर मिलेगा ✅</div></div>
<script src="https://checkout.razorpay.com/v1/checkout.js"></script><script>
var NOTE="{note}",TOK="{tok}",done=false,RZPKEY="{RZP_ID}";
function ok(){{done=true;document.querySelector(".c").innerHTML='<div style="text-align:center;padding:10px"><div style="font-size:40px">✅</div><h2>Payment Successful</h2><p style="color:#8fa1b8">Telegram जाओ — One-Time Join Link भेज दिया गया 🎟</p></div>';}}
function fail(t){{if(done)return;document.querySelector(".c").innerHTML='<div style="text-align:center;padding:10px"><div style="font-size:36px">⚠️</div><h2>'+t+'</h2><p style="color:#8fa1b8;font-size:14px">Dobara try kar sakte ho. Paisa kat gaya hai to page band MAT karo — 1-2 min me join link Telegram par apne aap mil jayega.</p><button id="retry" onclick="go()">🔄 Dobara try karein</button><button onclick="chk()" style="background:#2a3a52;margin-top:8px">📥 Status check</button></div>';}}
function chk(){{fetch("/pstatus?n="+encodeURIComponent(NOTE)+"&t="+encodeURIComponent(TOK)).then(function(x){{return x.json()}}).then(function(j){{if(j.paid){{ok()}}else{{fail("Payment abhi pending dikha raha hai")}}}}).catch(function(){{fail("Network me dikkat — thodi der me dobara check karein")}});}}
function pollPaid(){{var n=0,iv=setInterval(function(){{if(done){{clearInterval(iv);return;}}
 fetch("/pstatus?n="+encodeURIComponent(NOTE)+"&t="+encodeURIComponent(TOK)).then(function(x){{return x.json()}}).then(function(j){{if(j.paid){{clearInterval(iv);ok();}}}}).catch(function(){{}});
 if(++n>20){{clearInterval(iv);}}}},5000);}}
function openRp(oid){{var r=new Razorpay({{key:RZPKEY,order_id:oid,name:"AGRI LEARNING POINT",description:{json.dumps(b['title'][:70])},theme:{{color:"#13733e"}},
 handler:function(res){{fetch("/confirm?note="+encodeURIComponent(NOTE)+"&order_id="+res.razorpay_order_id+"&payment_id="+res.razorpay_payment_id+"&signature="+encodeURIComponent(res.razorpay_signature)).then(function(x){{return x.json()}}).then(function(j){{if(j.ok){{ok()}}else{{pollPaid();fail("Payment ho gayi — verify 1 min me complete ho jayega, page mat band karo")}}}}).catch(function(){{pollPaid()}});}},
 modal:{{ondie:function(){{if(!done&&!window.paying){{fail("Payment adhuri reh gayi")}}}}}}}});
 r.on("payment.failed",function(){{window.paying=false;fail("Payment fail ho gayi — dobara try karein")}});r.open();}}
function go(){{var bt=document.getElementById("pay");if(bt){{bt.disabled=true;bt.textContent="⏳ Server se connect ho raha hai…";}}
 fetch("/startpay?n="+encodeURIComponent(NOTE)+"&t="+encodeURIComponent(TOK)).then(function(x){{return x.json()}}).then(function(j){{if(bt){{bt.disabled=false;bt.textContent="💳 Pay ₹{b['price']} via Razorpay";}}
 if(j.order_id){{window.paying=true;openRp(j.order_id);}}else{{window.paying=false;fail(j.err||"Payment server busy hai");}}}}).catch(function(){{if(bt){{bt.disabled=false;bt.textContent="💳 Pay ₹{b['price']} via Razorpay";}}window.paying=false;fail("Payment server busy hai — dobara try karein");}});}}
document.getElementById("pay").onclick=go;
pollPaid();
</script></body></html>"""

def demo_page(note):
    uid, batch = int(note.split(":")[0]), note.split(":")[1]
    b = get_batches().get(batch) or {"title": "AGRI Batch", "price": 0}
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<body style='font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1621;color:#e9eef5;"
            f"display:flex;min-height:92vh;align-items:center;justify-content:center;margin:0'><div style='text-align:center;max-width:420px;padding:20px'>"
            f"<div style='font-size:40px'>💳</div><h2>Pay ₹{b['price']} — {_html.escape(b['title'])}</h2>"
            f"<p style='color:#8fa1b8'>DEMO payment page (Razorpay keys lagne par yahan real Razorpay checkout khulega)</p>"
            f"<a href='{PUB}/demopay?n={note}' style='display:inline-block;background:#8774e2;color:#fff;padding:13px 26px;border-radius:12px;font-weight:700;text-decoration:none'>✅ Pay ₹{b['price']} (simulate)</a>"
            f"</div></body>")

def poll_pending():
    if DEMO or not RZP_ID:
        return
    try:
        with db() as c:
            rows = c.execute("SELECT id,link,note FROM orders WHERE status='created' AND ts < ? ORDER BY id DESC LIMIT 5",
                             (time.time() - 45,)).fetchall()
        for oid, link, note in rows:
            if "/paydemo/" in (link or "") or not (link or "").startswith("order_"):
                continue
            try:
                o = _rzp_get(f"/orders/{link}")
            except Exception:
                continue
            if o.get("status") == "paid":
                uid, batch = int(note.split(":")[0]), note.split(":")[1]
                fulfill(uid, batch, note)
    except Exception:
        pass

# ---------------- main poll loop ----------------
OFF = 0
BEAT = [time.time()]          # heartbeat: watchdog kills+restarts if loop freezes
PHASE = ["boot"]              # where the loop currently is (visible at /admin/loopinfo)
LASTERR = [""]
_slow = threading.Lock()

def _bg(fn):
    """Run fn in a one-off daemon thread; skip if one is already running."""
    if _slow.acquire(blocking=False):
        def _w():
            try:
                fn()
            except Exception as e:
                print("bg err:", e)
            finally:
                _slow.release()
        threading.Thread(target=_w, daemon=True).start()
        return True
    return False

def _watchdog():
    while True:
        time.sleep(30)
        stuck = time.time() - BEAT[0]
        if stuck > 240:
            print(f"bot loop stuck {int(stuck)}s — hard restart (gunicorn respawns)", flush=True)
            os._exit(1)

def run(offset=None):
    global OFF
    if offset:
        OFF = offset
    PHASE[0] = "watchdog"
    threading.Thread(target=_watchdog, daemon=True).start()
    PHASE[0] = "pull"
    try:
        n = pull_github()
        if n:
            print(f"batches: {n} pulled from GitHub")
    except Exception:
        pass
    last_chk = 0
    PHASE[0] = "loop"
    while True:
        BEAT[0] = time.time(); PHASE[0] = "longpoll"
        try:
            rq = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={OFF}&timeout=28&allowed_updates=[\"message\",\"callback_query\",\"chat_join_request\"]")
            r = urllib.request.urlopen(rq, timeout=35)
            body = r.read(); r.close()
            BEAT[0] = time.time(); PHASE[0] = "dispatch"
            for u in json.loads(body).get("result", []):
                OFF = u["update_id"] + 1
                try:
                    handle(u)
                except Exception as e:
                    LASTERR[0] = "handle: " + str(e)[:200]; print("handle err:", e)
                BEAT[0] = time.time(); PHASE[0] = "dispatch"
        except Exception as e:
            LASTERR[0] = "getUpdates: " + str(e)[:200]
            BEAT[0] = time.time(); PHASE[0] = "retry"
            time.sleep(1)
        if time.time() - last_chk > 20:
            last_chk = time.time()
            _bg(poll_pending)   # NEVER in the bot loop thread
        PHASE[0] = "loop"

def handle(u):
    if "message" in u:
        m = u["message"]
        txt = (m.get("text") or "").lower().strip()
        uid = m["chat"]["id"]
        if uid == ADMIN_ID:
            admin_message(m); return
        # ---- public users: buttons/commands only, free text = silence (+forward) ----
        if txt.startswith("/start") or txt == "/batches":
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text=catalog_msg(), reply_markup=catalog_kb(uid)); return
        if txt in ("/help",):
            tg("sendMessage", chat_id=uid, text="Commands: /start · /batches · /status"); return
        if txt in ("/status", "/my"):
            with db() as c:
                rows = c.execute("SELECT batch,status,ts FROM orders WHERE uid=? ORDER BY id DESC LIMIT 8", (uid,)).fetchall()
            tg("sendMessage", chat_id=uid, parse_mode="HTML", text="📋 <b>Aapke orders</b>\n" +
               ("\n".join(f"• {_html.escape(get_batches().get(r[0], {}).get('title', r[0]))} — {r[1]}" for r in rows) or "Abhi koi order nahi."))
            return
        fwd = (m.get("text") or ("📷 photo bheja" if m.get("photo") else ("📄 document" if m.get("document") else "")))
        if fwd:
            hot = bool(re.search(r"(paid|pay|txn|utr|upi|reference|screenshot|link|error|problem|issue|help)", fwd, re.I))
            un = m.get("from", {}).get("username")
            tg("sendMessage", chat_id=ADMIN_ID, parse_mode="HTML",
               text=f"{'🔔' if hot else '📩'} <code>{uid}</code>{' @' + un if un else ''}: {_html.escape(str(fwd))[:400]}"
                    + (f"\n/reply — /give uid:batch:txn-note se link bhejo" if hot else ""))
        return
    if "chat_join_request" in u:
        jr = u["chat_join_request"]
        req_uid = jr["from"]["id"]
        chat_id = jr["chat"]["id"]
        title = jr["chat"].get("title", "")
        batch = next((k for k, b in get_batches().items() if str(b.get("chat", "")) == str(chat_id)), "")
        paid = False
        if batch:
            with db() as c:
                paid = bool(c.execute("SELECT 1 FROM orders WHERE uid=? AND batch=? AND status IN ('paid','delivered')",
                                      (req_uid, batch)).fetchone())
        if paid:
            tg("approveChatJoinRequest", chat_id=chat_id, user_id=req_uid)
            with db() as c:
                c.execute("UPDATE orders SET status='delivered' WHERE uid=? AND batch=? AND status='paid'", (req_uid, batch))
            tg("sendMessage", chat_id=req_uid, parse_mode="HTML",
               text=f"🎉 <b>Joined!</b> {_html.escape(title)} — welcome! Pinned rules padh lena 📌\nAb daily live tests me full speed 🚀")
            tg("sendMessage", chat_id=ADMIN_ID, parse_mode="HTML",
               text=f"✅ auto-approved <code>{req_uid}</code> → {_html.escape(str(title))} ({batch}, paid ✓)")
        elif req_uid == ADMIN_ID:
            tg("approveChatJoinRequest", chat_id=chat_id, user_id=req_uid)
        else:
            kb = {"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"jreq:ok:{chat_id}:{req_uid}:{batch}"},
                                       {"text": "🚫 Deny", "callback_data": f"jreq:no:{chat_id}:{req_uid}"}]]}
            tg("sendMessage", chat_id=ADMIN_ID, parse_mode="HTML",
               text=f"🙋 <b>Join request</b> — <code>{req_uid}</code> → {_html.escape(str(title))}\n"
                    + ("⚠️ iska paid order nahi mila — manual approve karo to bhejo txn dekhke" if batch else ""),
               reply_markup=kb)
        return
    if "callback_query" in u:
        q = u["callback_query"]
        uid = q["from"]["id"]
        data = q.get("data", "")
        if data.startswith("jreq:") and uid == ADMIN_ID:
            parts = data.split(":")
            if parts[1] == "ok":
                tg("approveChatJoinRequest", chat_id=int(parts[2]), user_id=int(parts[3]))
                if len(parts) > 4 and parts[4]:
                    with db() as c:
                        c.execute("UPDATE orders SET status='delivered' WHERE uid=? AND batch=? AND status='paid'", (int(parts[3]), parts[4]))
                    tg("sendMessage", chat_id=int(parts[3]), parse_mode="HTML", text="🎉 Admin ne join approve kar diya — welcome! 📌")
                tg("answerCallbackQuery", callback_query_id=q["id"], text="Approved ✓")
            else:
                tg("declineChatJoinRequest", chat_id=int(parts[2]), user_id=int(parts[3]))
                tg("answerCallbackQuery", callback_query_id=q["id"], text="Denied")
            return
        mid = q["message"]["message_id"]
        cid = q["message"]["chat"]["id"]
        if data == "cat":
            tg("editMessageText", chat_id=cid, message_id=mid, parse_mode="HTML", text=catalog_msg(), reply_markup=catalog_kb(uid))
        elif data.startswith("b:"):
            k = data[2:]
            if k in get_batches():
                tg("editMessageText", chat_id=cid, message_id=mid, parse_mode="HTML", text=batch_msg(k), reply_markup=batch_kb(k))
        elif data.startswith("p:"):
            k = data[2:]
            tg("answerCallbackQuery", callback_query_id=q["id"], text="⏳ Payment link taiyar ho raha hai…")
            link = make_pay_link(uid, k)
            if link and link.startswith("http"):
                tg("sendMessage", chat_id=uid, parse_mode="HTML",
                   text=f"🔐 <b>Secure Payment</b> — ₹{get_batches()[k]['price']} <i>(Razorpay)</i>\n\n"
                        f"💳 <a href=\"{link}\">Tap to pay now · अभी भुगतान करें</a>\n\n"
                        f"✅ Pay karte hi <b>One-Time Join Link</b> yahin milega\n"
                        f"✅ पेमेंट होते ही <b>जॉइन लिंक</b> यहीं मिलेगा", disable_web_page_preview=False)
            else:
                tg("answerCallbackQuery", callback_query_id=q["id"],
                   text="⚠️ Payment server thoda busy hai — 2 min baad dobara 'Pay' dabayein 🙏", show_alert=True)
        elif uid == ADMIN_ID and data.startswith("ad:"):
            admin_callback(q, data, cid, mid)

def admin_message(m):
    uid = m["chat"]["id"]; txt = (m.get("text") or "").strip(); low = txt.lower()
    if low.startswith(("/start", "/panel", "/help")):
        tg("sendMessage", chat_id=uid, parse_mode="HTML",
           text=("🛠 <b>ADMIN CONSOLE — SatyamSir</b>\n\n"
                 "Bot public users ke liye ready — unhe sirf buttons milenge, free-text pe bot chup rahega "
                 "(msg aapko forward ho jaayega).\n\n"
                 "<b>Mujhe normal language me bolo — main kar dunga:</b>\n"
                 "• <i>“AFO batch ki fees 299 kar do”</i>\n"
                 "• <i>“add batch: Soil Health Book ₹149, group -1003761821341”</i>\n"
                 "• <i>“RK Sharma batch hata do”</i>\n"
                 "• <i>“kitne orders aaj?”</i>\n\n"
                 "Commands: /panel /give <uid:batch:ts> /force <uid> <batch>"),
           reply_markup=panel_kb())
        return
    if low.startswith("/give ") or low.startswith("/force "):
        parts = txt.split()
        try:
            if low.startswith("/give"):
                note = parts[1]
                uid2, batch = int(note.split(":")[0]), note.split(":")[1]
                with db() as c:
                    c.execute("INSERT OR IGNORE INTO orders(uid,batch,link,status,note,ts) VALUES(?,?,?,?,?,?)",
                              (uid2, batch, "manual", "created", note, time.time()))
                fulfill(uid2, batch, note)
                tg("sendMessage", chat_id=uid, text="✅ fulfill() chala gaya — check buyer DM.")
            else:
                uid2, batch = int(parts[1]), parts[2]
                fulfill(uid2, batch, f"{uid2}:{batch}:manual")
                tg("sendMessage", chat_id=uid, text="✅ manual fulfill done")
        except Exception as e:
            tg("sendMessage", chat_id=uid, text=f"⚠️ {e}")
        return
    w = WAIT.get(uid)
    if w == "add":
        WAIT.pop(uid, None)
        res = admin_ai("add batch: " + txt)
        tg("sendMessage", chat_id=uid, parse_mode="HTML", text=res)
        return
    if w == "price":
        WAIT.pop(uid, None)
        res = admin_ai(txt)
        tg("sendMessage", chat_id=uid, parse_mode="HTML", text=res)
        return
    # general AI chat for admin
    out = admin_ai(txt)
    tg("sendMessage", chat_id=uid, parse_mode="HTML", text=out)

def admin_callback(q, data, cid, mid):
    if data == "ad:panel":
        tg("editMessageText", chat_id=cid, message_id=mid, parse_mode="HTML", text="🛠 <b>Admin Panel</b>", reply_markup=panel_kb())
    elif data == "ad:add":
        WAIT[cid] = "add"
        tg("answerCallbackQuery", callback_query_id=q["id"])
        tg("sendMessage", chat_id=cid, parse_mode="HTML",
           text=("➕ <b>Naya batch — details bhejo (koi bhi format):</b>\n"
                 "<code>Soil Health Book Batch ₹149 group -1003761821341</code>\n"
                 "Main samajh ke add + GitHub pe save kar dunga. Bot me turant dikhega 📦"))
    elif data == "ad:price":
        WAIT[cid] = "price"
        tg("answerCallbackQuery", callback_query_id=q["id"])
        tg("sendMessage", chat_id=cid, parse_mode="HTML",
           text="💰 <b>Batch + naya price bolo</b>, e.g. <code>AFO 299</code> · <code>malwa ki fees 199 kar do</code>")
    elif data == "ad:rem":
        tg("editMessageText", chat_id=cid, message_id=mid, parse_mode="HTML", text="🗑 <b>Hataane ke liye batch tap karo:</b>", reply_markup=remove_kb())
    elif data.startswith("ad:rm:"):
        b = del_batch(data[6:])
        tg("editMessageText", chat_id=cid, message_id=mid, parse_mode="HTML",
           text=f"🗑 Removed: <b>{_html.escape(b['title'])}</b> ✅ GitHub save." if b else "⚠️ key nahi mili", reply_markup=panel_kb())
    elif data == "ad:today":
        tg("sendMessage", chat_id=cid, parse_mode="HTML", text=admin_orders_today())
        tg("answerCallbackQuery", callback_query_id=q["id"])
    elif data == "ad:pull":
        n = pull_github()
        tg("answerCallbackQuery", callback_query_id=q["id"], text=f"Pulled {n} batches" if n else "No file on GitHub")
    elif data == "ad:push":
        ok = push_github(get_batches())
        tg("answerCallbackQuery", callback_query_id=q["id"], text="Pushed ✓" if ok else "Push failed (token?)")

if __name__ == "__main__":
    run()
