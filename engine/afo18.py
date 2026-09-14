#!/usr/bin/env python3
"""afo18 — FRESH v11 runner: AFO mains test @18:00 IST (locked T1/T2).
Group: @agriquizworld (-1003784795446) via EXAM bot (admin). Source: Mongo agri.afo_sets.
Rules honored: IST-only · 4-line announce pinned · countdown · 50 polls x 30s (open_period) ·
+2/-.5 · leaderboard 48/msg · congrats pinned · result FILE unpinned · short CTA ·
journal in state.json (git) = resume, never re-announce · missed after go+4h stays missed ·
lock (locked_by/lock_ts, heartbeat) = two cycles never run the test twice.
Modes: cycle (default) · --rearm (workflow's last step, always runs).
"""
import json, os, sys, time, html, urllib.request, urllib.error, datetime as dt, subprocess

DAY = "2026-09-14"
GO_UTC = 12.5 * 3600            # 18:00 IST = 12:30 UTC
CHAT = "-1003784795446"
B = "https://api.telegram.org/bot" + (os.environ.get("EXAM_TG_TOKEN") or "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state.json")
REPO = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
GH = os.environ.get("GITHUB_TOKEN", "")
ME = os.environ.get("GITHUB_RUN_ID", "?")
RIGHT, WRONG, NQ = 2.0, -0.5, 50


def now_ist():
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)


def log(*a):
    print(*a, flush=True)


# ---------- Telegram ----------
def tg(m, **kw):
    for i in range(4):
        try:
            req = urllib.request.Request(f"{B}/{m}",
                data=json.dumps({k: v for k, v in kw.items() if v is not None}).encode(),
                headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=25).read())
            if r.get("ok"):
                return r["result"]
            if "Too Many Requests" in str(r.get("description", "")):
                time.sleep(int(r.get("parameters", {}).get("retry_after", 3)) + 1); continue
            log("tg err", m, r.get("description")); return None
        except Exception as e:
            log("tg exc", m, str(e)[:80]); time.sleep(3)
    return None


def tg_file(path, **kw):
    bound = "kf11"
    fields = {k: str(v) for k, v in kw.items() if v is not None}
    body = b""
    for k, v in fields.items():
        body += f"--{bound}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    fn = os.path.basename(path)
    body += f"--{bound}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{fn}\"\r\nContent-Type: text/html\r\n\r\n".encode()
    body += open(path, "rb").read() + f"\r\n--{bound}--\r\n".encode()
    for i in range(4):
        try:
            req = urllib.request.Request(f"{B}/sendDocument", data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={bound}"})
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            if r.get("ok"):
                return r["result"]
            if "Too Many Requests" in str(r.get("description", "")):
                time.sleep(int(r.get("parameters", {}).get("retry_after", 3)) + 1); continue
            log("file err", r.get("description")); return None
        except Exception as e:
            log("file exc", str(e)[:80]); time.sleep(3)
    return None


# ---------- journal (state.json in git; runner-side) ----------
def jload():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def jref():
    global jsha
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/state.json",
            headers={"Authorization": f"Bearer {GH}"})
        d = json.loads(urllib.request.urlopen(req, timeout=25).read())
        jsha = d.get("sha")
        return json.loads(base64.b64decode(d["content"]).decode())
    except Exception:
        jsha = None
        return {}


def jget():
    st = jref()
    return st, (st.get("afo18") or {"step": 0, "qidx": 0})


def jput(st, j, note=""):
    st["afo18"] = j
    _save_push(st, note)


def _save_push(st, note):
    global jsha
    rj = jref()  # refresh sha + latest for conflict-smartness
    rj.setdefault("afo18", {})
    mine, theirs = st.get("afo18", {}), rj.get("afo18", {})
    if int(theirs.get("step", 0)) > int(mine.get("step", 0)):
        for k in ("step", "qidx", "msg_ann", "locked_by", "lock_ts"):
            if k in theirs:
                mine[k] = theirs[k]
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/state.json",
            data=json.dumps({"content": base64.b64encode(json.dumps(st, indent=0, sort_keys=True).encode()).decode(),
                             "message": "afo18: " + (note or "journal"),
                             **({"sha": jsha} if jsha else {})}).encode(),
            method="PUT", headers={"Authorization": f"Bearer {GH}", "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        log("journal push fail", e.code, e.read()[:120].decode())


# ---------- mongo ----------
def afo_set(date):
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=12000)["agri"]
    d = db.afo_sets.find_one({"date": date})
    return db, d


# ---------- cycles ----------
def secs_to_go():
    t = now_ist()
    return (GO_UTC - (t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6)) if t.strftime("%Y-%m-%d") == DAY else -1e9, t


def rearm():
    st, j = jget()
    d2g, t = secs_to_go()
    step = int(j.get("step", 0))
    if t.strftime("%Y-%m-%d") != DAY or step >= 8 or d2g > 4 * 3600:
        log("rearm: no further cycle (day/step/deadline ok)"); return
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/workflows/afo-today.yml/dispatches",
            data=json.dumps({"ref": "main"}).encode(), method="POST",
            headers={"Authorization": f"Bearer {GH}", "Content-Length": "0"})
        urllib.request.urlopen(req, timeout=20)
        log("rearm: dispatched next cycle")
    except Exception as e:
        log("rearm err", str(e)[:90])


def esc(s):
    return html.escape(str(s))


def run_test():
    st, j = jget()
    d2g, t = secs_to_go()
    if t.strftime("%Y-%m-%d") != DAY:
        log("not scheduled day; exit"); return
    step = int(j.get("step", 0))
    if step >= 8:
        log("already done"); return
    # lock: only one holder runs the exam; stale lock (2 min no heartbeat) may be taken over
    lk_by, lk_ts = j.get("locked_by"), float(j.get("lock_ts", 0))
    if lk_by and lk_by != ME and time.time() - lk_ts < 120:
        log("test running in another run; skip"); return
    j.update({"locked_by": ME, "lock_ts": time.time()})
    jput(st, j, "lock")
    db, doc = afo_set(DAY)
    if not doc or len(doc.get("questions") or []) < 10:
        log("FATAL: no afo set for", DAY); sys.exit(1)
    qs = doc["questions"][:NQ]

    if step < 1:
        ann = tg("sendMessage", chat_id=CHAT, parse_mode="HTML", disable_web_page_preview=True, text=(
            "🌆 <b>AFO MAINS TEST (NEW PATTERN)</b>\n"
            "📅 Aaj 14 September 2026 · ⏰ 6:00 PM IST sharp\n"
            "📝 50 questions · 30s each · ek answer · poll auto-close\n"
            "🏆 +2 right · −0.5 wrong · end me leaderboard + result file 📄"))
        if ann:
            try:
                tg("pinChatMessage", chat_id=CHAT, message_id=ann["message_id"])
            except Exception:
                pass
            j.update({"step": 1, "msg_ann": ann["message_id"]})
            jput(jref(), j, "announce")
        log("announce sent", j.get("msg_ann"))
    # countdown to GO (only if time remains)
    while True:
        d2g, t = secs_to_go()
        if d2g <= 0:
            break
        if d2g < 61 and int(j.get("cd", 0)) < 1:
            if j.get("msg_ann"):
                tg("editMessageText", chat_id=CHAT, message_id=j["msg_ann"], parse_mode="HTML", text=(
                    "🌆 <b>AFO MAINS TEST (NEW PATTERN)</b>\n📅 14 Sep 2026 · ⏰ 6:00 PM IST\n"
                    "📝 50Q · 30s · +2 / −0.5\n⏳ <b>START in " + str(int(d2g)) + "s…</b>"))
        time.sleep(min(int(d2g), 20))
        j["lock_ts"] = time.time()
        if int(d2g) <= 61:
            j["cd"] = 1
        if d2g <= 0:
            break

    # flush updates, then stream poll answers
    off = 0
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{B}/getUpdates?offset=-1", headers={}), timeout=15).read())
        off = (r["result"][-1]["update_id"] + 1) if r.get("result") else 0
    except Exception:
        pass
    scores, names, answered = {}, {}, {}   # qid -> uid -> opt
    for i in range(int(j.get("qidx", 0)), len(qs)):
        q = qs[i]
        opts = [esc(o) for o in (q.get("o") or [])[:5]]
        poll = tg("sendPoll", chat_id=CHAT, question=f"{i+1}/{len(qs)}. {esc(q['q'])[:300]}",
                  options=opts, type="regular", is_anonymous=False,
                  allows_multiple_answers=False, open_period=30)
        pid = poll["poll"]["id"] if poll else None
        end = time.time() + 29
        while time.time() < end:
            try:
                r = json.loads(urllib.request.urlopen(urllib.request.Request(
                    f"{B}/getUpdates?offset={off}&timeout=1", headers={}), timeout=8).read())
                for u in r.get("result") or []:
                    off = max(off, u["update_id"] + 1)
                    pa = u.get("poll_answer")
                    if pa and (not pid or pa.get("poll_id") == pid):
                        uid = str(pa["user"]["id"])
                        names[uid] = (pa["user"].get("username") or pa["user"].get("first_name") or "player")[:32]
                        chosen = (pa.get("option_ids") or [None])[0]
                        got = (chosen == q.get("key"))
                        answered.setdefault(str(i), {})[uid] = (chosen, got)
            except Exception:
                time.sleep(2)
        j.update({"qidx": i + 1, "step": 2, "lock_ts": time.time()})
        if (i + 1) % 5 == 0 or i + 1 == len(qs):
            jput(jref(), j, f"polls {i+1}")
    # score
    for qi, m in answered.items():
        for uid, (opt, got) in m.items():
            scores[uid] = scores.get(uid, 0.0) + (RIGHT if got else WRONG)
    for uid in list(names):
        scores.setdefault(uid, -0.5 * 0)
    rank = sorted(scores.items(), key=lambda kv: -kv[1]) if scores else []
    j.update({"step": 3}); jput(jref(), j, "polls-done")

    # leaderboard (48/msg)
    lines = [f"{chr(129351+int(k)) if int(k)<3 else str(int(k)+1)+'. '}<a href=\"tg://user?id={u}\">{esc(names.get(u,u))}</a> — <b>{s:+.1f}</b>"
             for k, (u, s) in enumerate(rank[:48])]
    for i in range(0, max(len(lines), 1), 48):
        hd = "🏆 <b>AFO MAINS — LEADERBOARD</b> (50Q, +2/−0.5)\n" if i == 0 else "🏆 leaderboard contd…\n"
        txt = hd + ("\n".join(lines[i:i+48]) if lines else "Abhi koi score nahi — kal 6 PM phir! 👀")
        tg("sendMessage", chat_id=CHAT, parse_mode="HTML", disable_web_page_preview=True, text=txt[:4000])
    j.update({"step": 4}); jput(jref(), j, "leaderboard")

    # congrats (pinned)
    c = tg("sendMessage", chat_id=CHAT, parse_mode="HTML", text=(
        "🎉 <b>AFO MAINS complete</b> — 50 sawal, sabko dhanyavaad! 🌾 "
        + (f"Topper: <b>{esc(names.get(rank[0][0],''))}</b> ({rank[0][1]:+.1f})" if rank else "")))
    if c:
        tg("pinChatMessage", chat_id=CHAT, message_id=c["message_id"])
    # result file (6065-style table), UNPINNED
    p = os.path.join(ROOT, f"AFO_Mains_{DAY}_results.html")
    rows = "".join(f"<tr><td>{k+1}</td><td>{esc(names.get(u,u))}</td><td>{s:+.1f}</td></tr>"
                   for k, (u, s) in enumerate(rank)) or "<tr><td colspan=3>no answers</td></tr>"
    key = "".join(f"<tr><td>{i+1}</td><td>{esc(qs[i]['q'])[:160]}</td><td><b>{esc(qs[i]['o'][qs[i]['key']] if qs[i].get('key') is not None and qs[i]['key'] < len(qs[i]['o']) else '—')}</b></td></tr>"
                  for i in range(len(qs)))
    open(p, "w").write(f"<html><head><meta charset='utf-8'><title>AFO Mains {DAY}</title>"
        "<style>body{font-family:sans-serif;max-width:760px;margin:auto;padding:16px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;font-size:14px}</style></head>"
        f"<body><h2>🌆 AFO MAINS — {DAY} (IST)</h2><h3>Scores</h3><table><tr><th>#</th><th>Player</th><th>Net</th></tr>{rows}</table>"
        f"<h3>Answer Key</h3><table><tr><th>Q</th><th>Question</th><th>Correct</th></tr>{key}</table></body></html>")
    tg_file(p, chat_id=CHAT, caption="📄 AFO MAINS result + answer key — 14 Sep 2026 (unpinned by rule)")
    # short CTA
    tg("sendMessage", chat_id=CHAT, parse_mode="HTML", text="🌾 Roz: 11:00 AM Malwa Book · 2:30 PM IARI · 6:00 PM AFO Mains — @agriquizworld")
    j.update({"step": 8, "locked_by": "", "done_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    jput(jref(), j, "test-complete")
    try:
        db.afo_sets.update_one({"date": DAY}, {"$set": {"status": "used", "used_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}})
    except Exception as e:
        log("mongo mark err", str(e)[:60])
    log("DONE: AFO mains test complete")


def cycle():
    _, j = jget()
    d2g, t = secs_to_go()
    if t.strftime("%Y-%m-%d") != DAY or int(j.get("step", 0)) >= 8:
        log("cycle: idle"); return
    if d2g > 4 * 3600:
        j.update({"step": 8, "missed": True}); jput(jref(), j, "missed"); return
    if d2g > 200:                       # too early to start; just wait (short run)
        log(f"cycle: {int(d2g)}s to go — sleeping 150s"); time.sleep(150); return
    run_test()


if __name__ == "__main__":
    (rearm if "--rearm" in sys.argv else cycle)()
