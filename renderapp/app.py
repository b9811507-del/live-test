#!/usr/bin/env python3
"""livescore — Render service for LIVE TEST system.
Hosts: locked-until-GO test page, server-side grading (answer keys never leave server),
leaderboard API, health/keep-warm, offline /soon page. SQLite storage.
Admin endpoints require header X-Admin-Key == env ADMIN_KEY.
"""
import os, time, json, sqlite3, threading, re
from flask import Flask, request, jsonify, Response

APP = Flask(__name__)
BOOT_ERR = ""
try:
    import paidbot  # eager import: module fully initialized before threads/routes
except Exception as _e:
    import traceback
    BOOT_ERR = "eager: " + traceback.format_exc()[-400:]
    print("paidbot import failed:", _e)
DB = os.environ.get("DATA_PATH", os.path.join(os.path.dirname(__file__), "live.db"))
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
_lock = threading.Lock()

DAY_TTL_GRACE = 180          # late submissions accepted till go+dur+180s

def db():
    c = sqlite3.connect(DB, 6)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init():
    with _lock, db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS days(job TEXT, date TEXT, go REAL, dur REAL,"
                  " mark TEXT, payload TEXT, PRIMARY KEY(job,date))")
        c.execute("CREATE TABLE IF NOT EXISTS subs(job TEXT, date TEXT, name TEXT, final REAL,"
                  " right INTEGER, wrong INTEGER, att INTEGER, ts REAL, PRIMARY KEY(job,date,name))")

def _auth():
    return ADMIN_KEY and request.headers.get("X-Admin-Key", "") == ADMIN_KEY

def day_row(job, date):
    with db() as c:
        r = c.execute("SELECT go,dur,mark,payload FROM days WHERE job=? AND date=?",
                      (job, date)).fetchone()
    if not r:
        return None
    return {"go": r[0], "dur": r[1], "mark": json.loads(r[2]), "payload": json.loads(r[3])}

# ---------- public API ----------
@APP.get("/")
@APP.get("/healthz")
def health():
    with db() as c:
        n = c.execute("SELECT job||'/'||date, (SELECT COUNT(*) FROM subs s WHERE s.job=d.job AND s.date=d.date) FROM days d").fetchall()
    return jsonify({"ok": True, "t": round(time.time(), 1), "days": {k: v for k, v in n}})

@APP.get("/api/day")
def api_day():
    job, date = request.args.get("job", ""), request.args.get("date", "")
    d = day_row(job, date)
    if not d:
        return jsonify({"error": "no test for this day"}), 404
    now = time.time()
    if now < d["go"] - 1:                      # LOCKED till GO
        return jsonify({"locked": True, "go": d["go"], "now": now})
    p = d["payload"]
    qs = [{"q": q["q"], "o": q["o"]} for q in p["questions"]]   # key never sent
    return jsonify({"locked": False, "title": p.get("title", ""), "go": d["go"],
                    "dur": d["dur"], "deadline": d["go"] + d["dur"], "now": now,
                    "marks": d["mark"], "code": p.get("code", ""), "questions": qs})

@APP.post("/api/score")
def api_score():
    job, date = request.args.get("job", ""), request.args.get("date", "")
    d = day_row(job, date)
    if not d:
        return jsonify({"error": "no test"}), 404
    now = time.time()
    if now < d["go"] - 30:
        return jsonify({"error": "test has not started yet"}), 425
    if now > d["go"] + d["dur"] + DAY_TTL_GRACE:
        return jsonify({"error": "test window closed"}), 410
    b = request.get_json(force=True, silent=True) or {}
    name = str(b.get("name", ""))[:40].strip()
    answers = b.get("answers") or []
    if not name:
        return jsonify({"error": "name required"}), 400
    key = d["payload"]["key"]
    mr, mw = d["mark"]["right"], d["mark"]["wrong"]
    right = wrong = att = 0
    for i, k in enumerate(key):
        a = answers[i] if i < len(answers) else None
        if a is None or a < 0:
            continue
        att += 1
        if a == k:
            right += 1
        else:
            wrong += 1
    final = round(right * mr + wrong * mw, 2)
    with _lock, db() as c:
        if c.execute("SELECT 1 FROM subs WHERE job=? AND date=? AND name=?",
                     (job, date, name.lower())).fetchone():
            return jsonify({"error": "already submitted — first attempt only"}), 409
        c.execute("INSERT INTO subs VALUES(?,?,?,?,?,?,?,?)",
                  (job, date, name.lower(), final, right, wrong, att, now))
    return jsonify({"final": final, "right": right, "wrong": wrong, "att": att, "n": len(key)})

@APP.get("/api/board")
def api_board():
    job, date = request.args.get("job", ""), request.args.get("date", "")
    d = day_row(job, date)
    if not d:
        return jsonify({"error": "no test"}), 404
    with db() as c:
        rows = c.execute("SELECT name,final,right,wrong,att,ts FROM subs WHERE job=? AND date=?",
                         (job, date)).fetchall()
    rows.sort(key=lambda r: (-r[1], -r[2], r[3], r[0]))
    out = [{"name": r[0], "final": r[1], "right": r[2], "wrong": r[3],
            "att": r[4], "ts": r[5]} for r in rows]
    return jsonify({"job": job, "date": date, "n": len(out),
                    "deadline": d["go"] + d["dur"], "rows": out})

@APP.post("/rzp/webhook")
def rzp_hook():
    import paidbot, threading as _th
    b = dict(request.get_json(force=True) or {})
    b["_sig"] = request.headers.get("X-Razorpay-Signature", "")
    _th.Thread(target=paidbot.handle_webhook, args=(b,), daemon=True).start()
    return jsonify({"ok": True})   # ack fast; failures are covered by poll_pending backstop

@APP.get("/p/<note>/<tok>")
def pay_page(note, tok):
    import paidbot, hmac
    if not hmac.compare_digest(paidbot._tok(note), tok):
        return Response("<body style='font:16px sans-serif;background:#0f1621;color:#fff;text-align:center;padding:60px'>❌ Link expired / invalid</body>", mimetype="text/html")
    return Response(paidbot.checkout_page(note, tok), mimetype="text/html")

@APP.route("/confirm", methods=["GET", "POST"])
def confirm():
    import paidbot
    d = request.args if request.method == "GET" else (request.get_json(silent=True) or request.form)
    note, oid, pid, sig = d.get("note", ""), d.get("order_id", ""), d.get("payment_id", ""), d.get("signature", "")
    with paidbot.db() as c:
        row = c.execute("SELECT batch,uid,status FROM orders WHERE note=?", (note,)).fetchone()
    if not row or row[2] == "paid":
        return jsonify({"ok": row and row[2] == "paid"})
    if not paidbot.verify_sig(oid, pid, sig):
        paidbot._admin_alert(f"confirm bad signature note={note} order={oid}")
        return jsonify({"ok": False, "err": "bad signature"}), 400
    uid, batch = int(row[1]), row[0]
    paidbot.fulfill(uid, batch, note)
    return jsonify({"ok": True})

@APP.post("/startpay")
@APP.get("/startpay")
def startpay():
    """Lazily create the Razorpay order — runs in a web thread, never blocks the bot."""
    import paidbot, hmac
    d = request.args if request.method == "GET" else {**request.args.to_dict(), **(request.get_json(silent=True) or {})}
    note, t = d.get("n", ""), d.get("t", "")
    if not note or not hmac.compare_digest(paidbot._tok(note), t):
        return jsonify({"err": "bad link"}), 403
    try:
        return jsonify({"order_id": paidbot.ensure_rzp_order(note)})
    except Exception as e:
        msg = str(e)[:160].lower()
        friendly = "payment"
        if "expire" in msg or "closed" in msg:
            friendly = "order expire ho gaya — dobara dabayein"
        elif "busy" in msg or "timed" in msg or "read" in msg:
            friendly = "payment server busy hai — 1 min baad try karein"
        return jsonify({"err": friendly})

@APP.get("/pstatus")
def pstatus():
    """Lightweight payment-status poll used by the checkout page auto-recovery."""
    import paidbot, hmac
    note, t = request.args.get("n", ""), request.args.get("t", "")
    if not note or not hmac.compare_digest(paidbot._tok(note), t):
        return jsonify({"paid": False, "err": "bad token"}), 403
    with paidbot.db() as c:
        row = c.execute("SELECT status FROM orders WHERE note=?", (note,)).fetchone()
    st = row[0] if row else "none"
    return jsonify({"paid": st in ("paid", "delivered"), "status": st})

@APP.get("/paydemo/<path:note>")
def paydemo(note):
    import paidbot
    return Response(paidbot.demo_page(note), mimetype="text/html")

@APP.get("/demopay")
def demopay():
    import paidbot
    n = request.args.get("n", "")
    try:
        uid, batch = int(n.split(":")[0]), n.split(":")[1]
        paidbot.fulfill(uid, batch, n, paid=True)
    except Exception:
        pass
    return Response("<!doctype html><meta charset=utf-8><body style='font:17px/1.6 -apple-system;background:#0f1621;color:#e9eef5;display:flex;min-height:95vh;align-items:center;justify-content:center;margin:0'><div style='text-align:center'><div style='font-size:46px'>✅</div><h2>Payment Successful (demo)</h2><p style='color:#8fa1b8'>Telegram check karo — join link bhej diya gaya</p></div>",
                    mimetype="text/html")

@APP.post("/admin/selftest")
def admin_selftest():
    if not _auth():
        return jsonify({"error": "bad key"}), 403
    import traceback, io, contextlib, sys as _sys
    out = {}
    try:
        PM = _sys.modules.get("paidbot")
        out["in_sys_modules"] = bool(PM)
        out["attrs"] = sorted([k for k in vars(PM).keys() if not k.startswith("__")])[:25] if PM else None
        PB = __import__("paidbot")
        out["import"] = "ok"
        try:
            PB.db().execute("SELECT 1").fetchone(); out["sqlite"] = "ok"
        except Exception as e:
            out["sqlite"] = f"FAIL {e}"
        # LIVE payment path check: real ₹1 order create (retries included) + cancel
        try:
            if PB.RZP_ID and not PB.DEMO:
                oid_ = PB.api_post("/orders", {"amount": 100, "currency": "INR",
                                                "receipt": "selftest", "notes": {"ref": "selftest"}})["id"]
                cancel = "cancelled"
                try:
                    PB.api_post(f"/orders/{oid_}/cancel", {})
                except Exception:
                    cancel = "left-created(expire 15m)"
                out["rzp"] = f"live order {oid_} ok · {cancel}"
            else:
                out["rzp"] = "demo mode or no keys"
        except Exception as e:
            out["rzp"] = f"FAIL: {str(e)[:220]}"
        for name, upd in (("admin_start", {"message": {"chat": {"id": PB.ADMIN_ID}, "text": "/start", "from": {"id": PB.ADMIN_ID}}}),
                         ("user_start", {"message": {"chat": {"id": 12345}, "text": "/start batch", "from": {"id": 12345}}}),
                         ("user_chat", {"message": {"chat": {"id": 12346}, "text": "hello?", "from": {"id": 12346}}})):
            try:
                log = io.StringIO()
                with contextlib.redirect_stdout(log):
                    PB.handle(upd)
                out[name] = "ran: " + (log.getvalue()[:200] or "no-exception")
            except Exception as e:
                out[name] = "RAISE: " + traceback.format_exc(limit=4)[-400:]
    except Exception:
        out["fatal"] = traceback.format_exc()[-500:]
    return jsonify(out)


@APP.get("/admin/loopfix")
def admin_loopfix():
    """External breaker (keepwarm cron hits this): if the bot loop froze >150s, kill the
    worker so gunicorn respawns a fresh one. Cheap insurance that needs no threads."""
    if not _auth():
        return jsonify({"error": "bad key"}), 403
    import paidbot, time as _t
    age = _t.time() - paidbot.BEAT[0]
    if age > 150:
        print(f"loopfix: loop stuck {int(age)}s — respawning worker", flush=True)
        os._exit(1)
    return jsonify({"ok": True, "loop_age_s": round(age, 1)})

@APP.get("/admin/stackdump")
def admin_stackdump():
    """Exact line where every thread of this worker sits — ultimate freeze diagnostic."""
    if not _auth():
        return jsonify({"error": "bad key"}), 403
    import sys, threading, traceback
    frames = sys._current_frames()
    out = []
    for t in threading.enumerate():
        f = frames.get(t.ident)
        loc = ""
        if f:
            st = traceback.StackSummary.extract(traceback.walk_stack(f), limit=4, capture_locals=False)
            loc = " <- ".join(f"{s.filename.split('/')[-1]}:{s.lineno} in {s.name}" for s in st[:4])
        out.append(f"{t.name}: {loc}")
    return Response("\n".join(out), mimetype="text/plain")

@APP.get("/admin/loopinfo")
def admin_loopinfo():
    if not _auth():
        return jsonify({"error": "bad key"}), 403
    import paidbot
    procs = [d for d in os.listdir("/proc") if d.isdigit()]
    return jsonify({"loop_age_s": round(__import__("time").time() - paidbot.BEAT[0], 1),
                    "updates_off": paidbot.OFF, "phase": paidbot.PHASE[0],
                    "last_err": paidbot.LASTERR[0], "boot_id": getattr(paidbot, "BOOT_ID", "?"),
                    "pid": os.getpid(), "procs": len(procs),
                    "boot_err": BOOT_ERR[:600] or "(clean)",
                    "threads": __import__("threading").active_count()})

@APP.get("/admin/ping")
def admin_ping():
    if not _auth():
        return jsonify({"error": "bad key"}), 403
    import paidbot as PB
    r = PB.tg("sendMessage", chat_id=PB.ADMIN_ID, text="🤖 bot↔telegram link OK (self-test ping)")
    return jsonify({"send": r if isinstance(r, dict) else str(r)[:120], "admin": PB.ADMIN_ID})


@APP.get("/admin/nettest")
def admin_nettest():
    if not _auth():
        return jsonify({"error": "bad key"}), 403
    import socket, urllib.request as U
    out = {}
    t0 = time.time()
    try:
        ai = socket.getaddrinfo("api.telegram.org", 443)
        out["dns"] = [r[4][0] for r in ai][:4]
    except Exception as e:
        out["dns"] = f"FAIL {e}"
    for name, url in (("tg", "https://api.telegram.org/bot8533597307:AAF_8uqRRxlQ0dKQQm5-o9KEkUHrNqZKp0c/getMe"),
                      ("gen", "https://example.com"),
                      ("rzp", "https://api.razorpay.com")):
        try:
            body = U.urlopen(url, timeout=7).read()
            out[name] = f"ok {len(body)}B {round(time.time()-t0,1)}s"
        except Exception as e:
            out[name] = f"{type(e).__name__}: {str(e)[:80]}"
    out["total"] = round(time.time() - t0, 1)
    try:
        out["gai_fn"] = socket.getaddrinfo.__name__
    except Exception:
        pass
    return jsonify(out)


@APP.get("/soon")
def soon():
    return Response("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                    "<body style='font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1621;color:#e9eef5;"
                    "display:flex;min-height:90vh;align-items:center;justify-content:center;margin:0'>"
                    "<div style='text-align:center;padding:24px'><div style='font-size:44px'>🚧</div>"
                    "<h2>Batches opening soon</h2><p style='color:#8fa1b8'>Payment setup is being finished by the admin.<br>"
                    "Meanwhile keep appearing in daily LIVE tests 💪🌾</p></div>", mimetype="text/html")

# ---------- admin (engine -> server) ----------
@APP.post("/admin/day")
def admin_day():
    if not _auth():
        return jsonify({"error": "bad key"}), 403
    b = request.get_json(force=True)
    need = ("job", "date", "go", "dur", "questions", "key")
    if any(k not in b for k in need):
        return jsonify({"error": "missing " + ",".join(k for k in need if k not in b)}), 400
    if len(b["questions"]) != len(b["key"]) or not (2 <= len(b["questions"]) <= 200):
        return jsonify({"error": "sanity: q/key mismatch or count"}), 400
    for q in b["questions"]:
        if not q.get("q") or len(q.get("o", [])) < 2:
            return jsonify({"error": "sanity: bad question"}), 400
    payload = {"title": b.get("title", ""), "code": b.get("code", ""),
               "questions": [{"q": q["q"], "o": q["o"]} for q in b["questions"]],
               "key": [int(k) for k in b["key"]]}
    mark = b.get("mark") or {"right": 2, "wrong": -0.5}
    with _lock, db() as c:
        c.execute("INSERT OR REPLACE INTO days VALUES(?,?,?,?,?,?)",
                  (b["job"], b["date"], float(b["go"]), float(b["dur"]),
                   json.dumps(mark), json.dumps(payload)))
        if b.get("clear_subs"):
            c.execute("DELETE FROM subs WHERE job=? AND date=?", (b["job"], b["date"]))
    return jsonify({"ok": True, "job": b["job"], "date": b["date"],
                    "n": len(payload["questions"])})

@APP.get("/t/<job>/<date>")
def test_page(job, date):
    return Response(PAGE_HTML.replace("__JOB__", re.sub(r"\W", "", job)).replace("__DATE__", re.sub(r"[\W]", "", date)),
                    mimetype="text/html")

PAGE_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>LIVE TEST</title><style>
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;background:#0f1621;color:#e9eef5}
.wrap{max-width:560px;margin:0 auto;padding:14px 12px 80px}
.bar{position:fixed;top:0;left:0;right:0;background:#182333cc;backdrop-filter:blur(6px);padding:8px 12px;display:flex;justify-content:space-between;align-items:center;z-index:9;border-bottom:1px solid #ffffff14}
.bar b{font-size:13px}.t{font-variant-numeric:tabular-nums;color:#ffd76b;font-weight:700}
h1{font-size:16px;margin:52px 0 4px}.sub{color:#8fa1b8;font-size:12.5px;margin:0 0 12px}
.q{background:#182333;border-radius:12px;padding:12px;margin:0 0 10px}
.qn{font-size:11px;color:#8774e2;font-weight:700}
.qt{margin:2px 0 8px;white-space:pre-wrap;word-break:break-word}
.opt{display:block;padding:9px 10px;border:1px solid #ffffff17;border-radius:9px;margin:5px 0;font-size:14px;cursor:pointer}
.opt.sel{border-color:#8774e2;background:#8774e222}
button{width:100%;padding:14px;border:0;border-radius:12px;background:#8774e2;color:#fff;font-size:16px;font-weight:700;margin:10px 0}
button.sec{background:#202c42;font-weight:600}
#done,#lock{text-align:center;padding:40px 12px}
.big{font-size:40px}.sc{font-size:30px;font-weight:800;color:#7be495}
input{width:100%;padding:12px;border-radius:10px;border:1px solid #ffffff22;background:#0f1621;color:#e9eef5;font-size:15px;margin:8px 0}
.note{font-size:12px;color:#8fa1b8}
</style></head><body><div class="bar"><b id="ttl">LIVE TEST</b><span class="t" id="clk">--:--</span></div>
<div class="wrap" id="app"><div id="lock"><div class="big">🔒</div><h2>Test locked</h2><div class="note" id="lmsg">Please stay in the group — countdown starts in the chat.</div></div></div>
<script>
const JOB="__JOB__",DATE="__DATE__";let DAY=null,tmr=null;
const LS="lt_"+JOB+"_"+DATE;
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function fmt(s){s=Math.max(0,Math.floor(s));return (s/60|0)+":"+String(s%60).padStart(2,"0")}
async function load(){
 let r=await fetch("/api/day?job="+JOB+"&date="+DATE).then(x=>x.json());
 if(r.locked){document.getElementById("lmsg").textContent="Starts at "+new Date(r.go*1000).toLocaleTimeString()+". This page will refresh automatically.";setTimeout(load,4000);return}
 if(r.error){document.getElementById("lock").innerHTML="<div class='big'>😕</div>"+esc(r.error);return}
 DAY=r;document.getElementById("ttl").textContent=r.title||"LIVE TEST";render();
}
function saved(){try{return JSON.parse(localStorage.getItem(LS)||"{}")}catch(e){return{}}}
function persist(){localStorage.setItem(LS,JSON.stringify(S))}
let S=saved();
function render(){
 let a=document.getElementById("app");a.id="app";
 a.innerHTML="<h1>"+esc(DAY.title)+"</h1><p class='sub'>"+DAY.questions.length+" Q · "+(DAY.dur/60|0)+" min · ✅ +"+DAY.marks.right+" · ❌ "+DAY.marks.wrong+(DAY.code?" · 🆔 <b>"+esc(DAY.code)+"</b>":"")+"</p>"+
 DAY.questions.map((q,i)=>"<div class='q'><div class='qn'>Q"+(i+1)+"</div><div class='qt'>"+esc(q.q)+"</div>"+
 q.o.map((o,j)=>"<label class='opt"+(S[i]===j?" sel":"")+"' data-i="+i+" data-j="+j+"><input type=hidden>"+esc(o)+"</label>").join("")+"</div>").join("")+
 "<div id='subbox'><input id='nm' placeholder='Your name (as in group)' value='"+esc(S._nm||"")+"'><button id='go'>SUBMIT TEST</button><div class='note'>First submission only counts · auto-submits at time-up</div></div>";
 document.querySelectorAll(".opt").forEach(el=>el.onclick=()=>{let i=+el.dataset.i,j=+el.dataset.j;S[i]=S[i]===j?-1:j;persist();render()});
 document.getElementById("go").onclick=()=>submit(false);
 document.getElementById("nm").oninput=e=>{S._nm=e.target.value;persist()};
 tick();clearInterval(tmr);tmr=setInterval(tick,500);
}
function tick(){
 let left=DAY.deadline-Date.now()/1000;
 document.getElementById("clk").textContent=left>0?fmt(left):"0:00";
 if(left<=0){clearInterval(tmr);submit(true);}
}
async function submit(auto){
 clearInterval(tmr);
 let nm=(document.getElementById("nm")||{}).value||S._nm||"";
 if(!auto&&!nm.trim()){alert("Please enter your name to submit");return}
 let ans=DAY.questions.map((_,i)=>S[i]!==undefined&&S[i]>=0?S[i]:null);
 let body={name:nm.trim()||"Anon",answers:ans,auto:!!auto};
 try{
  let r=await fetch("/api/score?job="+JOB+"&date="+DATE,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(x=>x.json());
  if(r.error&&r.error.indexOf("already")>=0){done({final:"—",right:"?",wrong:"?",att:"?",n:DAY.questions.length},r.error);return}
  if(r.error){if(!auto){alert(r.error);return}setTimeout(()=>submit(true),8000);return}
  done(r);
 }catch(e){ if(!auto){alert("Network error — your answers are kept, press SUBMIT again");return} setTimeout(()=>submit(true),8000);}
}
function done(r,extra){
 document.getElementById("app").innerHTML="<div id='done'><div class='big'>✅</div><h2>Submitted!</h2>"+
 "<div class='sc'>"+r.final+"</div><p class='note'>Attempted "+r.att+" · ✅ "+r.right+" · ❌ "+r.wrong+" of "+r.n+
 (extra?"<br><i>"+esc(extra)+"</i>":"")+"</p><p class='note'>🏆 Leaderboard will be posted in the group right after the test ends.</p></div>";
 document.getElementById("clk").textContent="✅";localStorage.setItem(LS+"_sent","1");
}
load();
</script></body></html>"""

def bot_poller():
    """paid catalog bot — runs when PAID_BOT_TOKEN set (real handler in paidbot.py)."""
    global BOOT_ERR
    if not os.environ.get("PAID_BOT_TOKEN", ""):
        BOOT_ERR += " | no PAID_BOT_TOKEN"
        return
    try:
        import paidbot
        paidbot.BOOT_ID = os.environ.get("RENDER_DEPLOY_ID", "x") + "/" + str(os.getpid())
        paidbot.run()
        BOOT_ERR += " | run() RETURNED (should never)"
    except BaseException as e:      # BaseException: catch SystemExit too
        import traceback
        BOOT_ERR += " | poller: " + traceback.format_exc()[-500:]
        print("paidbot crashed:", e)

init()
app = APP  # alias so `gunicorn app:app` resolves
threading.Thread(target=bot_poller, daemon=True).start()

def post_fork(server, worker):
    """gunicorn imports in the master then FORKS workers — threads die at fork.
    Without this hook the bot poller lived (and froze) in the master's dead copy.
    (gunicorn calls post_fork inside each fresh worker)."""
    if os.environ.get("PAID_BOT_TOKEN", ""):
        threading.Thread(target=bot_poller, daemon=True).start()
        print(f"post_fork: bot poller (re)started in worker pid={os.getpid()}", flush=True)

if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
