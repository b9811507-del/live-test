#!/usr/bin/env python3
"""live-test engine v5 — POLL-BASED live tests in @agriquizworld (native Telegram quiz polls).
Format per user screenshots: each question = one quiz poll "Q<serial>: text", auto-closes 30s
after posting (open_period=30) → Telegram shows Final Results + correct ✅ like their past quizzes.
Bilingual: English sheet text + Google-translate Hindi (question + options). File msg NOT pinned.
State (pointers/journal/board) = state.json committed by Actions — git is the database.
Env: TG_TOKEN CHAT_ID ADMIN_CHAT RENDER_URL [GIT_TOKEN]
"""
import os, sys, csv, io, re, json, time, html, hashlib, random, subprocess, urllib.request, urllib.parse
import datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
import builder as BL

def _env(k, d=""):
    return os.environ.get(k, d)

TG_TOKEN = _env("TG_TOKEN", "8196655859:AAEG4T4HvWMS8e-sBlZTWT8FLdyrX5pWAKc")
CHAT = _env("CHAT_ID", "@agriquizworld")
ADMIN_CHAT = _env("ADMIN_CHAT")
RENDER = _env("RENDER_URL").rstrip("/")
TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))
def today(d=None): return (d or dt.datetime.now(TZ)).strftime("%Y-%m-%d")
def now(): return time.time()

JOBS = {
    "malwa": {"hh": 11, "mm": 0,  "emoji": "☀️", "right": 1, "wrong": -0.25, "label": "MALWA BOOK",
              "chain": ["malwa_vol1", "malwa_vol2", "malwa_horti"]},
    "iari":  {"hh": 14, "mm": 30, "emoji": "🌤", "right": 1, "wrong": -0.25, "label": "IARI BOOK MCQ 2026",
              "chain": ["iari"]},
    "afo":   {"hh": 18, "mm": 0,  "emoji": "🌆", "right": 2, "wrong": -0.5,  "label": "AFO MAINS TEST (NEW PATTERN)",
              "chain": None, "last_day": "2026-11-01"},
}
SHEETS = {
    "malwa_vol1": "128DIQLjlO0FfsTUReGbr2sHJcaJDg6WLjJc7CVRpNhg",
    "malwa_vol2": "1UgnIe-g8Fh0GiwtbQpSHgtlVtPk2hEngzBW5idqFD_E",
    "malwa_horti": "1YcJWVgWofbLkzOGeeDuPke7XPpyW_EETn9LeEEuz_dE",
    "nemraj":     "17U0MEc-3lXtKUH1WNBaHKNO25E7nS7BL2f9WymeGXY4",
    "rksharma":   "1bxM1Q-4hPwx9oTeTHuBFwyvJlYF6PuY1YfrNmvSaLlo",
    "iari":       "1sUgWskoLr7U16kVtKWb1o5-GItSv5UPumD9VCH3T4NI",
}
KEYBY_SID = {v: k for k, v in SHEETS.items()}
BOOK_TITLES = {"malwa_vol1": "MALWA BOOK VOL 1", "malwa_vol2": "MALWA BOOK VOL 2",
               "malwa_horti": "HORTICULTURE (MALWA)", "iari": "IARI BOOK MCQ 2026"}
AFO_EXCLUDE = re.compile(r"model\s*test", re.I)
TOP_TOPICS = 25
QPACE = 30
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state.json")
FILES_DIR = os.path.join(os.path.dirname(__file__), "gen")
os.makedirs(FILES_DIR, exist_ok=True)

def log(*a): print(f"[{dt.datetime.now(TZ):%H:%M:%S}]", *a, flush=True)

# ---------------- HTTP ----------------
def _req(url, data=None, headers=None, method=None, timeout=60):
    rq = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(rq, timeout=timeout) as f:
        return json.loads(f.read() or b"{}")

def tg(method, files=None, **kw):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    for attempt in range(6):
        try:
            if files:
                boundary = "engine-b"; parts = []
                for k, v in kw.items():
                    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
                for k, (fn, blob) in files.items():
                    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: text/html\r\n\r\n".encode() + blob + b"\r\n")
                parts.append(f"--{boundary}--\r\n".encode())
                r = _req(url, data=b"".join(parts), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            else:
                r = _req(url, data=json.dumps({k: v for k, v in kw.items() if v is not None}).encode(),
                         headers={"Content-Type": "application/json"})
            if r.get("ok"):
                return r["result"]
            if r.get("error_code") == 429:
                time.sleep(r.get("parameters", {}).get("retry_after", 3) + 1); continue
            if "message is not modified" in r.get("description", ""):
                return {"message_id": kw.get("message_id")}
            raise RuntimeError(f"{method}: {r.get('description')}")
        except RuntimeError:
            raise
        except Exception as e:
            log(f"tg {method} retry{attempt}: {e}")
            if "400" in str(e) and attempt >= 2:
                raise
            time.sleep(3 + 2 * attempt)
    raise RuntimeError(f"tg {method}: retries exhausted")

# ---------------- translator (Google free; CACHE-ONLY at live — network only when NET=True prebuild)
_tc = {}
NET = False
TC_BUDGET = 0
_tr_logged = False
def tr_hi(txt):
    global TC_BUDGET
    txt = (txt or "").strip()
    if len(txt) < 3 or re.search(r"[\u0900-\u097F]", txt):
        return ""
    k = hashlib.md5(txt.encode()).hexdigest()[:16]
    if k in _tc:
        return _tc[k]
    if not NET or (TC_BUDGET and now() > TC_BUDGET):
        return ""                     # live path: instant fallback, pacing never breaks
    out = ""
    try:
        u = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=hi&dt=t&q="
             + urllib.parse.quote(txt[:700]))
        try:
            d = _req(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            out = "".join(x[0] or "" for x in d[0] if x[0])
        except Exception as e:
            global _tr_logged
            if "429" in str(e):
                TC_BUDGET = 1          # endpoint limiting us: stop all network translating this run
            if not _tr_logged:
                _tr_logged = True
                log("translate endpoint limited — rest of this run stays EN-only (test never breaks)")
    except Exception as e:
        log("translate fail (EN-only):", e)
    out = re.sub(r"\s*[।.。]+$", "", out or "").strip()
    _tc[k] = out
    return out

def bl_q(en, sn=None):
    hi = tr_hi(en)
    base = (f"Q{sn}: " if sn is not None else "") + en
    s = base if not hi else f"{base}  |  {hi}"
    return s[:300] if hi else base[:300]

def bl_opt(en):
    hi = tr_hi(en)
    s = en if not hi else f"{en} ({hi})"
    return s[:100]

# ---------------- state ----------------
def load_state():
    try:
        with open(STATE_PATH) as f:
            st = json.load(f)
    except Exception:
        return {}
    for k, v in (st.get("tc") or {}).items():
        _tc.setdefault(k, v)
    return st

def save_state(st, msg="state update"):
    st["tc"] = dict(list(_tc.items())[-25000:])
    with open(STATE_PATH, "w") as f:
        json.dump(st, f, indent=1, ensure_ascii=False)
    repo = _env("GITHUB_REPOSITORY")
    if _env("GITHUB_ACTIONS") and repo:
        git = lambda *a: subprocess.run(("git",) + a, capture_output=True, text=True, check=False)
        git("add", "state.json")
        subprocess.run(("git", "-c", "user.name=live-test-bot", "-c", "user.email=bot@local",
                        "commit", "-m", msg), capture_output=True)
        tok = _env("GITHUB_TOKEN")
        for _ in range(5):
            subprocess.run(("git", "fetch", "origin", "main"), capture_output=True)
            subprocess.run(("git", "rebase", "origin/main"), capture_output=True)
            r = subprocess.run(("git", "push", f"https://runner:{tok}@github.com/{repo}", "HEAD:main"),
                               capture_output=True, text=True)
            if r.returncode == 0:
                break
            time.sleep(2 + 2 * random.random())
    elif _env("GIT_TOKEN"):
        repo = repo or "b9811507-del/live-test"
        try:
            sha = _req(f"https://api.github.com/repos/{repo}/contents/state.json",
                       headers={"Authorization": f"Bearer {_env('GIT_TOKEN')}", "Accept": "application/vnd.github+json"}).get("sha")
        except Exception:
            sha = None
        import base64
        body = json.dumps({"message": msg, "content": base64.b64encode(open(STATE_PATH, "rb").read()).decode(),
                           **({"sha": sha} if sha else {})}).encode()
        _req(f"https://api.github.com/repos/{repo}/contents/state.json", data=body, method="PUT",
             headers={"Authorization": f"Bearer {_env('GIT_TOKEN')}", "Content-Type": "application/json",
                      "Accept": "application/vnd.github+json"})

def jd(st, date, job):
    return st.setdefault("days", {}).setdefault(date, {}).setdefault(job, {})

# ---------------- sheets ----------------
_csv_cache, _title_cache = {}, {}

def fetch_csv(sid):
    if sid in _csv_cache:
        return _csv_cache[sid]
    err = None
    for gid in (None, 0):
        u = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv" + (f"&gid={gid}" if gid is not None else "")
        try:
            txt = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read().decode("utf-8-sig")
            if txt.startswith("<") or len(txt) < 500:
                continue
            _csv_cache[sid] = txt
            return txt
        except Exception as e:
            err = e
    key = KEYBY_SID.get(sid, "")
    local = os.path.join(os.path.dirname(__file__), "..", "data", f"{key}.csv")
    if key and os.path.exists(local):
        log(f"sheet {key}: live fetch failed ({err}) — using repo copy")
        _csv_cache[sid] = open(local, encoding="utf-8-sig").read()
        return _csv_cache[sid]
    raise RuntimeError(f"sheet fetch failed {sid}")

def live_title(sid):
    if sid in _title_cache:
        return _title_cache[sid]
    t = None
    try:
        h = urllib.request.urlopen(f"https://docs.google.com/spreadsheets/d/{sid}/htmlview", timeout=30).read().decode("utf-8", "replace")
        m = re.search(r"<title>(.*?)</title>", h, re.S | re.I)
        if m:
            t = re.sub(r"\s*[–-]\s*(Google Sheets|Google Drive)\s*$", "", m.group(1)).strip() or None
    except Exception:
        pass
    t = t or BOOK_TITLES.get(KEYBY_SID.get(sid, ""), "LIVE TEST")
    _title_cache[sid] = t
    return t

def parse_page(v):
    v = (v or "").strip().replace("\u2013", "-").replace("\u2014", "-")
    if not v:
        return None
    a, _, b = v.partition("-")
    a, b = (a.strip(), b.strip()) if _ else (v, v)
    try:
        lo, hi = int(float(a)), int(float(b))
    except ValueError:
        return None
    if lo <= 0 or hi <= 0:
        return None
    if hi < lo:
        lo, hi = hi, lo
    if hi - lo > 1:
        lo = max(hi - 1, 1)
    return (lo, hi)

def rows(sid):
    global _raw_by_uid
    out = []
    _raw_by_uid = {}
    for r in csv.DictReader(io.StringIO(fetch_csv(sid))):
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        r["_src"] = sid[:8]
        pg = parse_page(r.get("Book Page", ""))
        r["_pl"], r["_ph"] = (pg if pg else (0, 0))
        try:
            r["_sn"] = int(float(r.get("Serial No", "0")))
        except ValueError:
            r["_sn"] = len(out)
        if r.get("Question"):
            out.append(r)
    out.sort(key=lambda r: (r["_ph"], r["_sn"]))
    return out

_raw_by_uid = {}
def raw_by_uid(sid, rs=None):
    d = {}
    for r in (rs if rs is not None else rows(sid)):
        d[f"{sid[:8]}:{r['_sn']}"] = r
    d.update(_raw_by_uid)
    return d

OPT_LETTER = re.compile(r"^\(?\s*([a-eA-E])\b")
def resolve_key(row, opts):
    a = row.get("Correct Answer", "")
    m = OPT_LETTER.match(a)
    if m and opts and ord(m.group(1).lower()) - 97 < len(opts):
        return ord(m.group(1).lower()) - 97
    for i, o in enumerate(opts):
        if o and a and (a.lower() == o.lower() or a.lower() in o.lower() or o.lower() in a.lower()):
            return i
    return -1

def clean(s):
    s = (s or "").replace("\r", " ").replace("\n", " / ").strip()
    return re.sub(r"\s{2,}", " ", s)[:900]

def question_from_row(r):
    opts = [o for o in (r.get(f"Option {L}", "") for L in "ABCDE") if o]
    if len(opts) < 2:
        return None
    k = resolve_key(r, opts)
    if k < 0:
        return None
    q = {"uid": f"{r['_src']}:{r['_sn']}", "sn": r["_sn"], "q": clean(r["Question"]), "o": [clean(o) for o in opts],
         "key": k, "exp": clean(r.get("Explanation", ""))[:400], "page": r["_ph"], "topic": r.get("Topic", "")}
    _raw_by_uid.setdefault(q["uid"], r)
    return q

# ---------------- planners ----------------
def book_batches(sid):
    rs = rows(sid)
    by = {}
    for r in rs:
        if r["_ph"]:
            by.setdefault(r["_ph"], []).append(r)
    pages = sorted(by)
    lo_by = {p: min(x["_pl"] for x in by[p]) for p in pages}
    any_range = any(lo_by[p] != p for p in pages)
    out, cur, cur_lo, wend = [], [], None, None
    for p in pages:
        if any_range:
            if cur and lo_by[p] > wend and (wend - cur_lo + 1) >= 3:
                out.append(cur); cur = []
            if not cur:
                cur_lo = wend = lo_by[p]
            wend = max(wend, p)
            cur.append(p)
        else:
            if wend is None or p > wend:
                if cur:
                    out.append(cur)
                wend = (p - 1) // 3 * 3 + 3
                cur = []
            cur.append(p)
    if cur:
        out.append(cur)
    b = []
    for pgs in out:
        qs = [q for q in (question_from_row(r) for r in rs if r["_ph"] in pgs) if q]
        if qs:
            b.append({"pages": [min(lo_by.get(p, p) for p in pgs), max(pgs)], "questions": qs})
    return b

def build_book_day(job, st):
    cfg = JOBS[job]
    ptr = st.setdefault("ptr", {}).setdefault(job, {"book": cfg["chain"][0], "bidx": 0})
    chain = cfg["chain"]
    while True:
        if ptr["book"] not in chain:
            ptr["book"], ptr["bidx"] = chain[0], 0
        b = book_batches(SHEETS[ptr["book"]])
        if ptr["bidx"] < len(b):
            batch = b[ptr["bidx"]]
            return {"book": ptr["book"], "bidx": ptr["bidx"], "pages": batch["pages"],
                    "questions": batch["questions"], "n_batches": len(b)}
        nxt = chain[chain.index(ptr["book"]) + 1:]
        if not nxt:
            return None
        ptr["book"], ptr["bidx"] = nxt[0], 0

def afo_pool():
    rs, seen = [], set()
    for sid in list(SHEETS.values()):
        try:
            src = rows(sid)
        except Exception as e:
            log("pool: sheet unavailable, skipping", KEYBY_SID.get(sid, "?")); continue
        for r in src:
            if AFO_EXCLUDE.search(r.get("Topic", "")) or not r.get("Topic"):
                continue
            t = re.sub(r"[^a-z0-9]+", " ", r["Topic"].lower()).strip()
            key = (t, r["Question"][:60].lower())
            if key in seen:
                continue
            seen.add(key)
            q = question_from_row(r)
            if q:
                q["_t"] = t
                rs.append(q)
    cnt = {}
    for q in rs:
        cnt[q["_t"]] = cnt.get(q["_t"], 0) + 1
    top = {t for t, _ in sorted(cnt.items(), key=lambda x: -x[1])[:TOP_TOPICS]}
    pool = [q for q in rs if q["_t"] in top]
    for q in pool:
        q.pop("_t", None)
    return pool

def build_afo_day(st, date):
    a = st.setdefault("afo", {"cursor": 0, "seed": 20260911, "closed": False})
    if a.get("closed") or date > JOBS["afo"]["last_day"]:
        return None
    pool = afo_pool()
    order = sorted(pool, key=lambda q: hashlib.sha256(f"{a['seed']}|{q['uid']}".encode()).hexdigest())
    sel = order[a["cursor"]: a["cursor"] + 50] or order[:50]
    a["cursor"] = min(a["cursor"] + 50, len(order) - 1)
    return {"pages": None, "questions": sel, "n_batches": len(order) // 50, "book": None}

def day_meta(job, st, date, pretranslate=False):
    d = build_book_day(job, st) if JOBS[job]["chain"] else build_afo_day(st, date)
    if d:
        d["title"] = live_title(SHEETS[d["book"]]) if job != "afo" else "AFO MAINS TEST (NEW PATTERN)"
        if pretranslate and NET:
            n = 0
            for q in d["questions"]:
                for txt in [q["q"]] + q["o"]:
                    tr_hi(txt); n += 1
                    if TC_BUDGET and now() > TC_BUDGET:
                        log(f"pretranslate budget stop at {n} strings"); return d
                    time.sleep(0.2)
    return d

# ---------------- offline file (NOT pinned) ----------------
def gen_offline_file(job, date, day):
    """6065-format: full textbook-style template app (timer, themes, offline)."""
    raws = dict(_raw_by_uid)
    rowsp, DATA = [], []
    for q in day["questions"]:
        r = raws.get(q["uid"])
        if r is not None:
            rowsp.append((r["_ph"] or q.get("page") or 1, r))
    if rowsp:
        DATA, _bad = BL.build_questions(rowsp)
    if not DATA:                                  # fallback: build from parsed questions
        DATA = [{"s": q.get("sn", i + 1), "p": q.get("page", 0), "t": q.get("topic", ""), "q": q["q"],
                 "o": q["o"], "k": ["A", "B", "C", "D", "E"][:len(q["o"])], "a": q["key"], "e": q.get("exp", "")}
                for i, q in enumerate(day["questions"])]
    pages_per = {}
    if day.get("pages"):
        for r in raws.values():
            for p in range(max(r["_pl"], 1), r["_ph"] + 1):
                pages_per[p] = pages_per.get(p, 0) + 1
    book = f"{day['title']} \u2014 LIVE TEST"
    p = day.get("pages")
    slug = f"live_{job}_{'p%dp%d' % tuple(p) if p else date.replace('-','')}"
    name = f"LIVE_{('p%d-%d' % tuple(p)) if p else 'AFO'}_{date}_{len(DATA)}Q.html"
    path = os.path.join(FILES_DIR, name)
    BL.render_html(DATA, pages_per, book, "By SatyamSir", "Agri Learning Point", QPACE, slug, path)
    return path, name

# ---------------- messages ----------------
def fmt_date(d):
    try:
        dd = dt.date.fromisoformat(d)
        return f"{dd.day}-{dd.strftime('%b')}-{dd.year}"
    except ValueError:
        return d

def announce_text(job, date, day):
    """NEAT & PROFESSIONAL — 4 lines only (user order): title / By / date+pages / marks. No instructions."""
    cfg = JOBS[job]
    n = len(day["questions"])
    B = lambda s: f"<b>{s}</b>"
    pages = f" · {B('Pages %d-%d' % tuple(day['pages']))}" if day.get("pages") else ""
    L = [f"🎯 {B(day['title'] + ' — LIVE TEST')}",
         f"🖊 {B('By SatyamSir')}",
         f"📅 {B(fmt_date(date))}{pages}",
         f"⚡ {B(str(n) + ' Questions')} · {B('30 Sec/Question')} · ✅ {B('+' + str(cfg['right']))} · ❌ {B(str(cfg['wrong']))}"]
    return "\n".join(L)

def leaderboard_msgs(job, date, day, rows_, part=48):
    cfg = JOBS[job]
    B = lambda s: f"<b>{s}</b>"
    hdr = (f"🏆 {B('LIVE TEST LEADERBOARD — ' + day['title'] + f' ({fmt_date(date)}) · {len(day['questions'])} Q')}\n"
           f"⏱ 30 sec/Q · ✅ +{cfg['right']} · ❌ {cfg['wrong']}\n━━━━━━━━━━━━━━━━━━━━━━")
    msgs = []
    n = len(rows_)
    npart = max(1, (n + part - 1) // part)
    for pi in range(npart):
        chunk = rows_[pi * part:(pi + 1) * part]
        h = hdr if pi == 0 else f"🏆 {B('LEADERBOARD %d/%d — %s (%s)' % (pi + 1, npart, day['title'], fmt_date(date)))}\n━━━━━━━━━━━━━━━━━━━━━━"
        lines = [h]
        for k, r in enumerate(chunk):
            rank = pi * part + k + 1
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank)
            nm = html.escape(r["name"])
            head = f"{medal} {B(nm)}" if medal else f"{B(str(rank) + '.')} {B(nm)}"
            lines.append(f"{head}\n└ {B('%.2f' % r['final'])} | Att: {r['att']} | ✅ {r['right']} | ❌ {r['wrong']}")
        if pi < npart - 1:
            lines.append(f"<i>*{n - (pi + 1) * part} more → next message…*</i>")
        msgs.append("\n".join(lines))
    return msgs

def congrats_msg(rows_):
    if not rows_:
        return "💪 <b>Great Effort!</b> Test ho gaya — koi vote nahi mila isliye board khaali 😅 Kal phir! 🔜"
    B = lambda s: f"<b>{s}</b>"
    med = ["🥇", "🥈", ""]
    lines = [f"🎉 {B('CONGRATULATIONS TO OUR TOP %d RANKERS!' % min(3, len(rows_)))}", ""]
    for i, r in enumerate(rows_[:3]):
        lines.append(f"{B('Rank ' + str(i + 1) + ':')} {med[i]} {html.escape(r['name'])} — {B('%.2f' % r['final'])}")
    lines += ["", "Keep up the great work! 💪🌾"]
    return "\n".join(lines)

def cta_msg(job):
    """SHORT version — user order: 2 lines + join paid batches."""
    kind = "Live" if job == "afo" else "Book"
    return (f"💪 <b>Great Effort! {kind} Test Completed Successfully</b>\n"
            f"Consistency is the real test 📈\n"
            f"<i>Join paid batches 👇</i>")

def tomorrow_msg(st, date):
    try:
        nd = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
        L = [f"🔜 <b>Tomorrow ({dt.date.fromisoformat(nd).strftime('%A')}, {fmt_date(nd)})</b>"]
    except ValueError:
        nd, L = date, ["🔜 <b>Next slot</b>"]
    for job in ("malwa", "iari", "afo"):
        cfg = JOBS[job]
        tmr = peek_next(st, job, nd)
        if tmr is None:
            L.append(f"{cfg['emoji']} {cfg['hh']:02d}:{cfg['mm']:02d} — {cfg['label']}: 🏁 series completed ✅")
        elif job == "afo":
            L.append(f"{cfg['emoji']} {cfg['hh']:02d}:{cfg['mm']:02d} — AFO MAINS · <b>50 fresh Q</b> (30 sec/Q)")
        else:
            L.append(f"{cfg['emoji']} {cfg['hh']:02d}:{cfg['mm']:02d} — {tmr['title']} · <b>Pages {tmr['pages'][0]}-{tmr['pages'][1]}</b> · {len(tmr['questions'])} Q")
    L.append("🔁 Same time, same place 💪")
    return "\n".join(L)

def peek_next(st, job, date):
    save = json.dumps(st)
    try:
        cfg = JOBS[job]
        if cfg["chain"]:
            p = st.setdefault("ptr", {}).setdefault(job, {"book": cfg["chain"][0], "bidx": 0})
            st["ptr"][job] = {**p, "bidx": p["bidx"] + 1}
            r = build_book_day(job, st)
        else:
            a = st.setdefault("afo", {"cursor": 0, "seed": 20260911, "closed": False})
            st["afo"]["cursor"] = a.get("cursor", 0) + 50
            r = build_afo_day(st, date)
        if r:
            r["title"] = live_title(SHEETS[r["book"]]) if job != "afo" else "AFO MAINS TEST (NEW PATTERN)"
        return r
    except Exception as e:
        log("peek fail:", e); return None
    finally:
        st.clear(); st.update(json.loads(save))

def send(text, reply_markup=None, pin=False):
    r = tg("sendMessage", chat_id=CHAT, text=text, parse_mode="HTML", disable_web_page_preview=True,
           reply_markup=reply_markup)
    if pin:
        try: tg("pinChatMessage", chat_id=CHAT, message_id=r["message_id"])
        except Exception as e: log("pin fail", e)
    return r["message_id"]

def rotate_pins(st, job, new_ids):
    for mid in st.get("pins_prev", {}).get(job, []):
        try: tg("unpinChatMessage", chat_id=CHAT, message_id=mid)
        except Exception: pass
    st.setdefault("pins_prev", {})[job] = new_ids

def countdown(job, day, go):
    txt0 = f"⏳ <b>{day['title']}</b> starts in\n\n<b>1️⃣5️⃣ seconds</b>"
    mid = send(txt0)
    for lbl, at in (("1️⃣2️⃣", 11), ("9️⃣", 7.5), ("6️⃣", 4), ("3️⃣", 2), ("1️⃣", 0.6)):
        while now() < go - at:
            time.sleep(0.3)
        tg("editMessageText", chat_id=CHAT, message_id=mid, parse_mode="HTML",
           text=txt0.replace("1️⃣5️⃣", lbl))
    while now() < go:
        time.sleep(0.2)
    tg("editMessageText", chat_id=CHAT, message_id=mid, parse_mode="HTML",
       text=f"🚀 <b>TEST START</b> — pehla poll abhi aaya! ⏱ 30 sec me answer de do ✅")

# ---------------- poll engine + vote tracking ----------------
def run_test(st, date, job, day):
    """posts one quiz poll per question, 30s apart; collects poll_answer updates; returns rows."""
    cfg = JOBS[job]
    qs = day["questions"]
    by_poll = {}
    votes = {}            # user_id -> {"name":.., "a": {q_idx: [opts]}, }
    off = 0
    try:
        lst = _req(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?limit=1&offset=-1", timeout=12).get("result", [])
        if lst:
            off = lst[-1]["update_id"] + 1
    except Exception:
        pass
    start = now()
    for i, q in enumerate(qs):
        due = start + i * QPACE
        while now() < due:
            off = drain_votes(votes, off)
            time.sleep(max(0.05, min(1.0, due - now())))
        qq = bl_q(q["q"], q["sn"])
        opts = [bl_opt(o) for o in q["o"]]
        expl = f"✅ Sahi: {'ABCDE'[q['key']]}) {q['o'][q['key']][:60]}"
        if q.get("exp"):
            expl += " · " + q["exp"][:180]
        try:
            r = tg("sendPoll", chat_id=CHAT, question=qq[:300], options=json.dumps(opts),
                   type="quiz", correct_option_id=q["key"], is_anonymous=False, open_period=QPACE,
                   explanation=expl[:250])
            by_poll[r["poll"]["id"]] = i
            log(f"poll {i+1}/{len(qs)} Q{q['sn']} sent msg={r['message_id']}")
        except Exception as e:
            log(f"poll send fail Q{q['sn']}: {e} — retry once")
            try:
                r = tg("sendPoll", chat_id=CHAT, question=qq[:300], options=json.dumps(opts),
                       type="quiz", correct_option_id=q["key"], is_anonymous=False, open_period=QPACE,
                       explanation=expl[:250])
                by_poll[r["poll"]["id"]] = i
            except Exception as e2:
                log("giving up poll", e2)
    end = start + len(qs) * QPACE + 8
    while now() < end:
        off = drain_votes(votes, off)
        time.sleep(0.5)
    off = drain_votes(votes, off)
    mr, mw = cfg["right"], cfg["wrong"]
    res = {}
    for uid, v in votes.items():
        perq = {}
        for pid, sel in v["a"].items():
            qi = by_poll.get(pid)
            if qi is None or qi in perq:
                continue
            perq[qi] = qs[qi]["key"] in sel
        right = sum(1 for ok in perq.values() if ok)
        wrong = sum(1 for ok in perq.values() if not ok)
        res[uid] = {"name": v["name"], "right": right, "wrong": wrong, "att": right + wrong,
                   "final": round(right * mr + wrong * mw, 2)}
    rows_ = sorted(res.values(), key=lambda r: (-r["final"], -r["right"], r["wrong"], r["name"].lower()))
    j = jd(st, date, job)
    j["votes"] = {str(k): v for k, v in res.items()}
    return rows_

def drain_votes(votes, off):
    """single non-blocking getUpdates; 409/other = skip quietly (pace must not break)"""
    try:
        u = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?limit=100&timeout=0"
        if off:
            u += f"&offset={off}"
        upd = _req(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=12).get("result", [])
    except Exception:
        return off
    for u in upd:
        off = max(off, u["update_id"] + 1)
        a = u.get("poll_answer")
        if not a:
            continue
        uid = a["user"]["id"]
        nm = (a["user"].get("first_name") or "Student")[:40]
        v = votes.setdefault(uid, {"name": nm, "a": {}})
        v["name"] = nm
        v["a"].setdefault(a["poll_id"], set()).update(a["option_ids"])
    return off

# ---------------- slot steps (idempotent journal) ----------------
def ensure_day(st, date, job):
    j = jd(st, date, job)
    if j.get("step", 0) >= 1:
        return j, None
    day = day_meta(job, st, date)
    if day is None:
        return None, None
    n = len(day["questions"])
    go = slot_go(job, date)
    j.update({"step": 0, "go": go, "deadline": go + n * QPACE, "nq": n, "title": day["title"],
              "pages": day.get("pages"), "book": day.get("book"), "bidx": day.get("bidx", 0),
              "n_batches": day.get("n_batches", 0), "sn": [q["uid"] for q in day["questions"]]})
    return j, day

def slot_go(job, date, override=None):
    if override:
        return override
    y, m, d = map(int, date.split("-"))
    return dt.datetime(y, m, d, JOBS[job]["hh"], JOBS[job]["mm"], tzinfo=TZ).timestamp()

def rebuild_questions(st, date, job):
    j = jd(st, date, job)
    sn = set(j.get("sn", []))
    if JOBS[job]["chain"]:
        qs = [q for q in (question_from_row(r) for r in rows(SHEETS[j["book"]])) if q and q["uid"] in sn]
    else:
        qs = [q for q in (question_from_row(r) for sid in SHEETS.values() for r in rows(sid)) if q and q["uid"] in sn]
    order = {u: i for i, u in enumerate(j.get("sn", []))}
    qs = sorted({q["uid"]: q for q in qs}.values(), key=lambda q: order.get(q["uid"], 999))
    return {"questions": qs, "pages": j.get("pages"), "title": j.get("title", JOBS[job]["label"]),
            "book": j.get("book"), "bidx": j.get("bidx", 0), "n_batches": j.get("n_batches", 0)}

def step_finish(st, date, job, rows_):
    j = jd(st, date, job)
    if j.get("step", 0) >= 8:
        log(f"{job}/{date}: already complete"); return
    day = rebuild_questions(st, date, job)
    pins = []
    if j.get("step", 0) < 4:
        msgs = leaderboard_msgs(job, date, day, rows_)
        stats = f"👥 <b>{len(rows_)}</b> ne vote kiye" + (f" · 📊 avg {sum(r['final'] for r in rows_)/len(rows_):.1f} · 🥇 {rows_[0]['final']:.2f}" if rows_ else "")
        ids = []
        for i, m in enumerate(msgs):
            if i == 0:
                m += "\n" + stats
            ids.append(send(m, pin=True))
            time.sleep(1.2)
        pins += ids
        j.update({"step": 4, "msg_board": ids})
        save_state(st, f"{job} {date} leaderboard")
    if j.get("step", 0) < 5:
        cid = send(congrats_msg(rows_), pin=True); pins.append(cid)
        j.update({"step": 5, "msg_congrats": cid}); save_state(st, f"{job} {date} congrats")
    if j.get("step", 0) < 6:
        path, name = gen_offline_file(job, date, day)
        n = len(day["questions"])
        cap = (f"📗 *{day['title']} — LIVE TEST*\n" +
               (f"Pages {day['pages'][0]}–{day['pages'][1]}" if day.get("pages") else f"{n} MCQs · all-subject mix") +
               f"  ·  {n} MCQs  ·  {BL.fmt(n * QPACE)} timer\nBy SatyamSir\nOpen the file in any browser — works offline.")
        fid = send_file(path, name, cap)          # NOT pinned per user
        j.update({"step": 6, "msg_file": fid}); save_state(st, f"{job} {date} file")
    if j.get("step", 0) < 7:
        kb = {"inline_keyboard": [[{"text": "🎟 JOIN NOW — Paid Batches", "url": "https://t.me/Quizbotagri2_bot?start=batch"}]]}
        cid = send(cta_msg(job), reply_markup=kb)
        j.update({"step": 7, "msg_cta": cid}); save_state(st, f"{job} {date} cta")
    if j.get("step", 0) < 8:
        tid = send(tomorrow_msg(st, date), pin=True); pins.append(tid)
        j.update({"step": 8, "msg_tomorrow": tid})
        rotate_pins(st, job, pins)
        if JOBS[job]["chain"]:
            st["ptr"][job] = {"book": j.get("book"), "bidx": j.get("bidx", 0) + 1}
        else:
            st["afo"]["done_dates"] = st.get("afo", {}).get("done_dates", []) + [date]
            if date >= JOBS["afo"]["last_day"]:
                st["afo"]["closed"] = True
                try:
                    send("🏁 <b>AFO MAINS LIVE SERIES — COMPLETED</b>\n\n1-Nov tak roz shaam 6 baje 50 polls — thanks for showing up daily! 💪\nSeries ka overall champion: <b>" + series_champ(st) + "</b> ")
                except Exception as e:
                    log("close msg", e)
        save_state(st, f"{job} {date} finish")
        log(f"{job}/{date}: finish complete · {len(rows_)} voters")

def series_champ(st):
    tot = {}
    for d, jobs in st.get("days", {}).items():
        for uid, v in (jobs.get("afo", {}) or {}).get("votes", {}).items():
            t = tot.setdefault(uid, [0, v["name"]])
            t[0] += v["final"]
    return max(tot.values())[1] if tot else "—"

def send_file(path, name, caption, pin=False):
    blob = open(path, "rb").read()
    r = tg("sendDocument", {"document": (name, blob)}, chat_id=CHAT, caption=caption, parse_mode="Markdown")
    if pin:
        try: tg("pinChatMessage", chat_id=CHAT, message_id=r["message_id"])
        except Exception as e: log("pin fail", e)
    return r["message_id"]

# ---------------- commands ----------------
def cmd_run(job):
    st = load_state()
    date = today()
    if job == "afo" and (st.get("afo", {}).get("closed") or date > JOBS["afo"]["last_day"]):
        log("afo closed/past end — skip"); return
    j, day = ensure_day(st, date, job)
    if j is None:
        send(f"🏁 <b>{JOBS[job]['label']}</b> — poori series complete! 🎉 Series khatam — thanks for the daily consistency 💪🌾", pin=True)
        st.setdefault("finished", {})[job] = date; save_state(st, f"{job} finished"); return
    save_state(st, f"{job} {date} plan")
    if not day:
        day = rebuild_questions(st, date, job)
    target = j["go"] - 45
    if now() < target:
        time.sleep(min(target - now(), 3600))
    if j.get("step", 0) < 1:
        mid = send(announce_text(job, date, day), pin=True)
        j.update({"step": 1, "msg_ann": mid}); save_state(st, f"{job} {date} announce")
    rows_ = None
    if j.get("step", 0) < 3:
        countdown(job, day, j["go"])
        rows_ = run_test(st, date, job, day)
        j.update({"step": 3}); save_state(st, f"{job} {date} test-done")
    st = load_state()
    if rows_ is None:
        j2 = jd(st, date, job)
        cfg = JOBS[job]
        rows_ = sorted(({"name": v["name"], **{k: v[k] for k in ("right", "wrong", "att", "final")}}
                        for v in (j2.get("votes") or {}).values()),
                       key=lambda r: (-r["final"], -r["right"], r["wrong"], r["name"].lower()))
    step_finish(st, date, job, rows_)
    save_state(st, f"{job} {date} done")

def cmd_agent():
    st = load_state()
    date = today()
    fixes, problems = [], []
    for job in JOBS:
        if job == "afo" and (st.get("afo", {}).get("closed") or date > JOBS["afo"]["last_day"]):
            continue
        j = jd(st, date, job)
        go = j.get("go") or slot_go(job, date)
        if j.get("step", 0) < 8:
            if j.get("step", 0) == 0 and now() < go - 120:
                continue
            try:
                cmd_run(job); fixes.append(f"{job}: resumed (step {j.get('step',0)})")
            except Exception as e:
                problems.append(f"{job}: {e}")
    if _env("GITHUB_ACTIONS") and _env("GITHUB_TOKEN") and _env("GITHUB_REPOSITORY"):
        try:
            repo = _env("GITHUB_REPOSITORY")
            runs = _req(f"https://api.github.com/repos/{repo}/actions/runs?status=failure&per_page=3",
                        headers={"Authorization": f"Bearer {_env('GITHUB_TOKEN')}"})["workflow_runs"]
            for r in runs[:3]:
                if time.time() - dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).timestamp() < 8 * 3600:
                    _req(f"https://api.github.com/repos/{repo}/actions/runs/{r['id']}/rerun-failed-jobs",
                         data=b"{}", method="POST", headers={"Authorization": f"Bearer {_env('GITHUB_TOKEN')}", "Accept": "application/vnd.github+json"})
                    fixes.append(f"retried run {r['name']}")
        except Exception as e:
            problems.append(f"gh rerun: {e}")
    st.setdefault("agent_log", []).append({"t": time.strftime("%F %T"), "fixes": fixes, "problems": problems})
    st["agent_log"] = st["agent_log"][-40:]
    if problems and ADMIN_CHAT and now() - st.get("last_digest", 0) > 3600:
        try:
            tg("sendMessage", chat_id=ADMIN_CHAT, parse_mode="HTML",
               text=f"🛠 <b>live-test agent</b> {date}: " + "\n• ".join(html.escape(p) for p in problems) +
                    (("\n✔ fixed: " + "; ".join(fixes)) if fixes else ""))
            st["last_digest"] = now()
        except Exception as e:
            log("digest fail", e)
    save_state(st, "agent pass")
    log("agent:", fixes, problems)

def cmd_keepwarm():
    if not RENDER:
        print("no render"); return
    try:
        print("render:", _req(RENDER + "/healthz", timeout=15).get("ok"))
    except Exception as e:
        print("render down:", e)

def cmd_status():
    st = load_state()
    print(json.dumps({"ptr": st.get("ptr"), "afo": {k: v for k, v in st.get("afo", {}).items() if k != "done_dates"},
                      "today": {d: {job: {k: v for k, v in j.items() if k != 'votes'} for job, j in jobs.items()}
                                 for d, jobs in list(st.get("days", {}).items())[-2:]},
                      "agent": st.get("agent_log", [])[-1]}, indent=1, ensure_ascii=False))

def cmd_prebuild(job):
    global NET, TC_BUDGET
    NET = True
    TC_BUDGET = now() + int(_env("TRANSLATE_BUDGET_S", "900"))   # budget then continue anyway
    st = load_state()
    date = today()
    for k, v in (st.get("tc") or {}).items():
        _tc[k] = v                    # warm from committed cache — most days need ~0 fetches
    j = jd(st, date, job)
    if j.get("step", 0) >= 1:
        print("already planned"); return
    if job == "afo" and (st.get("afo", {}).get("closed") or date > JOBS["afo"]["last_day"]):
        print("afo closed"); return
    day = day_meta(job, st, date, pretranslate=True)
    if day is None:
        print("chain finished flag"); st.setdefault("finished", {})[job] = date; save_state(st, f"{job} finished"); return
    log(f"prebuild {job}: {len(day['questions'])}Q translated/cached")
    save_state(st, f"prebuild {job} {date}")

if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "status"
    a = sys.argv[2:]
    if c == "prebuild":
        cmd_prebuild(a[0])
    elif c == "run":
        cmd_run(a[0])
    elif c == "finish":   # resume only
        st = load_state()
        date = today()
        j = jd(st, date, a[0])
        if j.get("step", 0) >= 3:
            cfg = JOBS[a[0]]
            rows_ = sorted(({"name": v["name"], **{k: v[k] for k in ("right", "wrong", "att", "final")}}
                            for v in (j.get("votes") or {}).values()),
                           key=lambda r: (-r["final"], -r["right"], r["wrong"], r["name"].lower()))
            step_finish(st, date, a[0], rows_)
    elif c == "agent":
        cmd_agent()
    elif c == "keepwarm":
        cmd_keepwarm()
    else:
        cmd_status()
