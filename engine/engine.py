#!/usr/bin/env python3
"""AGRI QUIZ DAILY EXAM SYSTEM v11 — single engine. Runs ONLY as GitHub Actions steps.

No server. state.json in git = the only database. Sources: Google Sheets (read-only CSV) + MongoDB (AFO bank).

LOCKED (SPEC v11 §5/§6/§7):
  * all clocks/labels/day-keys/file names = IST (UTC+5:30); IST computed from utcnow()+330min, host clock never trusted.
  * slots: malwa 11:00 (vol1->vol2->horti) · iari 14:30 (5 pages/day) · afo 18:00 (50Q/-0.5).
    window: go-50min .. go+4h; after go+4h the slot is sealed MISSED forever (never retro-fired).
  * 30s per question, one poll open at a time, live scoring while open, last answer per user wins.
  * announce = 4 lines, pinned · polls unpinned · leaderboard 48 rows/msg · congrats pinned ·
    result FILE (6065 HTML) sent UNPINNED + one short CTA · nothing else, never two copies.
  * journal steps: 1 announced / 2 polls running (qidx each 5Q + lock heartbeat <=120s) / 3 polls done /
    4 leaderboard done / 8 complete. A crashed run RESUMES from the journal, never re-announces.
  * Telegram = EXAM bot (EXAM_TG_TOKEN) to CHAT_ID (-1003784795446) only. Webhook stays deleted;
    getUpdates is drained by exactly one process at a time (no 409).

Subcommands:
  slotchain                 one scheduler cycle (gates all 3 jobs, prebuild+run/resume)
  rearm [force]             dispatch the next slot-chain cycle (self-chaining scheduler)
  run <job>                 run/resume one job now (used by slotchain; manual debugging)
  prebuild <job>            fetch+freeze the day's questions into the journal (posts nothing)
  status                    journal + bank summary (never posts)
  ready                     live gate: can the bot post/pin in the target group?
  guard                     slot-guard watchdog pass
  agent                     maintenance pass (keepwarm job)
  keepwarm                  Render keepwarm ping + agent pass
  supply                    AFO bank audit/top-up (never posts to Telegram)
  booksend <job> <range> <step> [chat]   manual one-off book-file delivery
"""
import base64
import csv
import datetime as dt
import html
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # sibling modules (builder, afo_mongo)

VERSION = "v11"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state.json")
OUTDIR = os.path.join(ROOT, "out")
REPO = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local-%d" % os.getpid())
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

NOW_OVERRIDE = os.environ.get("ENGINE_NOW", "").strip()          # fake clock: ISO IST start instant
SPEED = float(os.environ.get("ENGINE_FAKE_SPEED", "1") or 1)     # fake clock: virtual seconds per real second
FAKE = os.environ.get("ENGINE_FAKE", "") == "1"                  # offline: no Telegram/Mongo/Sheets network
FAKE_LOG = os.environ.get("ENGINE_FAKE_LOG", "")                 # jsonl of every "telegram" call in fake mode
FAKE_MEMBER = os.environ.get("ENGINE_FAKE_MEMBER", "administrator")   # getChatMember status in fake mode
FAKE_SHEETS = os.environ.get("ENGINE_FAKE_SHEETS", "")           # dir with <sid>.csv fixtures
FAKE_TG_FILE = os.environ.get("ENGINE_FAKE_TG_FILE", "")         # file-backed fake bank used by afo_mongo
_T0 = time.time()

# --------------------------------------------------------------------------- config
CHAT_LOCKED = "-1003784795446"                 # @agriquizworld — ALL tests run here (locked)
CHAT = (os.environ.get("CHAT_ID", "").strip() or CHAT_LOCKED)
if CHAT != CHAT_LOCKED:
    print("WARN chat_for(): CHAT_ID=%r != locked %r -> using locked value" % (CHAT, CHAT_LOCKED), flush=True)
    CHAT = CHAT_LOCKED
ADMIN_CHAT = os.environ.get("ADMIN_CHAT", "").strip()
IARI_CHAT = os.environ.get("IARI_CHAT", "").strip()
RENDER_URL = os.environ.get("RENDER_URL", "").strip()
TOKEN = os.environ.get("EXAM_TG_TOKEN", "").strip()
API = "https://api.telegram.org/bot" + TOKEN
GH_API = "https://api.github.com/repos/" + REPO

SHEETS = {
    "malwa_vol1": "128DIQLjlO0FfsTUReGbr2sHJcaJDg6WLjJc7CVRpNhg",
    "malwa_vol2": "1UgnIe-g8Fh0GiwtbQpSHgtlVtPk2hEngzBW5idqFD_E",
    "malwa_horti": "1YcJWVgWofbLkzOGeeDuPke7XPpyW_EETn9LeEEuz_dE",
    "iari": "1sUgWskoLr7U16kVtKWb1o5-GItSv5UPumD9VCH3T4NI",
    "nemraj": "17U0MEc-3lXtKUH1WNBaHKNO25E7nS7BL2f9WymeGXY4",
    "rksharma": "1bxM1Q-4hPwx9oTeTHuBFwyvJlYF6PuY1YfrNmvSaLlo",
}
SHEET_HEADERS = ["serial", "page", "topic", "q", "o1", "o2", "o3", "o4", "o5", "key", "expl"]
VOLUMES = [("malwa_vol1", "MALWA BOOK VOL 1"), ("malwa_vol2", "MALWA BOOK VOL 2"),
           ("malwa_horti", "MALWA HORTICULTURE")]

JOBS = {
    "malwa": {"go": 11 * 3600, "time_label": "11:00 AM IST", "emoji": "☀️", "kind": "sheet-rotate",
              "right": 1.0, "wrong": -0.25, "n": 20, "batch": 150},
    "iari": {"go": 14 * 3600 + 30 * 60, "time_label": "2:30 PM IST", "emoji": "🌤", "kind": "sheet-pages",
             "right": 1.0, "wrong": -0.25, "pages_per_day": 5, "sid": "iari", "label": "IARI BOOK MCQ 2026"},
    "afo": {"go": 18 * 3600, "time_label": "6:00 PM IST", "emoji": "🌆", "kind": "mongo", "right": 2.0,
            "wrong": -0.5, "n": 50, "last_day": "2026-11-01", "label": "AFO MAINS TEST (NEW PATTERN)"},
}
ORDER = ["malwa", "iari", "afo"]
WINDOW_BEFORE = 50 * 60          # start allowed from go-50min
WINDOW_AFTER = 4 * 3600          # after go+4h a missed slot stays missed
POLL_SECONDS = 30                # open_period + drain window
LB_ROWS = 48                     # leaderboard rows per message
TEST_BUDGET = 55 * 60            # hard budget for announce+countdown+polls
CD_MAX = 55 * 60                 # max time spent waiting for go with announce already pinned


class EngineError(Exception):
    pass


# --------------------------------------------------------------------------- time / log
def istnow():
    if NOW_OVERRIDE:
        base = dt.datetime.fromisoformat(NOW_OVERRIDE)
        if base.tzinfo is None:
            base = base.replace(tzinfo=IST)
        return (base.astimezone(IST) + dt.timedelta(seconds=(time.time() - _T0) * SPEED))
    return dt.datetime.now(dt.timezone.utc).astimezone(IST)


def sleep(sec):
    """time.sleep, sped up by the fake clock (SPEED>1) and capped so a stuck run cannot hang the job."""
    sec = max(0.0, min(float(sec), 300.0))
    if SPEED > 1:
        sec = min(sec / SPEED, 300.0)
    time.sleep(sec)


def daykey(t=None):
    return (t or istnow()).strftime("%Y-%m-%d")


def go_dt(day, job):
    d = dt.date.fromisoformat(day)
    return dt.datetime(d.year, d.month, d.day, tzinfo=IST) + dt.timedelta(seconds=JOBS[job]["go"])


def day_label(day):
    d = dt.date.fromisoformat(day)
    return ("%s %s %s" % (d.day, d.strftime("%B"), d.year))


def hms(t):
    return t.strftime("%H:%M:%S")


def log(*a):
    print("[%s] [%s] %s" % (hms(istnow()), RUN_ID, " ".join(str(x) for x in a)), flush=True)


def esc(s):
    return html.escape(str(s if s is not None else ""))


def fmt_num(v):
    """1.0 -> '1', 2.0 -> '2', 0.5 -> '0.5' (locked group text shows +1 / +2, not +1.0)."""
    return "%g" % float(v)


def fmt_pair(right, wrong):
    """Locked scoring text: '+1 / −0.25' … '+2 / −0.5' (typographic minus, as in the spec)."""
    return "+%s / %s" % (fmt_num(right), ("−" + fmt_num(abs(float(wrong)))) if float(wrong) < 0 else fmt_num(wrong))


# --------------------------------------------------------------------------- fake telegram (offline battery)
_fake_ids = [1000]


def _fake_updates(params):
    """Synthetic poll_answer updates for the last poll (two players: one right, one wrong)."""
    pid = _last_poll.get("id")
    if not pid or params.get("offset") in (None, -1):
        return []
    users = [("9001", "TestAlpha", 0), ("9002", "TestBeta", 1)]
    return [{"update_id": _fake_ids[0] + 10 + i, "poll_answer": {
        "poll_id": pid, "user": {"id": int(u), "first_name": n, "username": None}, "option_ids": [o]}}
        for i, (u, n, o) in enumerate(users)]


_last_poll = {}


def _fake_tg(method, params):
    entry = {"t": istnow().isoformat(timespec="seconds"), "method": method,
             "chat": str(params.get("chat_id") or ""), "message_id": params.get("message_id"),
             "text": params.get("text"), "caption": params.get("caption"), "question": params.get("question"),
             "options": params.get("options"), "open_period": params.get("open_period")}
    if method in ("sendMessage", "sendPoll", "sendDocument", "sendPhoto"):
        _fake_ids[0] += 1
        entry["message_id"] = _fake_ids[0]
        if method == "sendPoll":
            _last_poll["id"] = "poll%d" % _fake_ids[0]
            _last_poll["q"] = params.get("question")
    if FAKE_LOG:
        with open(FAKE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if method == "getMe":
        return {"id": 8585018636, "is_bot": True, "username": "Arunkatyanquiz_bot", "first_name": "Premium batch"}
    if method == "getChatMember":
        return {"status": FAKE_MEMBER, "can_pin_messages": FAKE_MEMBER in ("administrator", "creator"),
                "can_delete_messages": FAKE_MEMBER in ("administrator", "creator"),
                "user": {"id": 8585018636, "is_bot": True, "username": "Arunkatyanquiz_bot"}}
    if method == "getChat":
        return {"id": int(CHAT), "title": "AGRI QUIZ WORLD", "type": "supergroup",
                "permissions": {"can_send_messages": False, "can_send_polls": False, "can_pin_messages": False}}
    if method == "getUpdates":
        return {"result": _fake_updates(params)}
    if method in ("sendMessage", "sendDocument", "sendPhoto"):
        return {"message_id": _fake_ids[0]}
    if method == "sendPoll":
        return {"message_id": _fake_ids[0], "poll": {"id": _last_poll["id"]}}
    if method in ("editMessageText", "editMessageCaption", "pinChatMessage", "unpinChatMessage",
                  "deleteMessage", "sendChatAction"):
        return {"message_id": params.get("message_id"), "ok_": True}
    return {"ok_": True}


# --------------------------------------------------------------------------- telegram
def tg(method, tries=5, **params):
    """Bot API call with 429 retry_after backoff + 5xx/timeout retries. Returns result|None. Never logs tokens."""
    params = {k: v for k, v in params.items() if v is not None}
    if FAKE:
        return _fake_tg(method, params)
    last = ""
    for i in range(tries):
        try:
            data = json.dumps(params).encode()
            req = urllib.request.Request(API + "/" + method, data=data,
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "agri-quiz-v11"})
            r = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
            if r.get("ok"):
                return r["result"]
            desc = str(r.get("description", ""))
            last = desc
            if r.get("error_code") == 429 or "Too Many Requests" in desc:
                wait = int((r.get("parameters") or {}).get("retry_after", 3)) + 1
                log("tg 429 %s -> sleep %ss" % (method, wait))
                time.sleep(wait)
                continue
            log("tg err %s: %s" % (method, desc[:140]))
            if "not enough rights" in desc.lower() or "chat not found" in desc.lower() or "bot was kicked" in desc.lower():
                return None
            time.sleep(1.5)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            last = "HTTP %s %s" % (e.code, body)
            if e.code == 429:
                time.sleep(4)
                continue
            log("tg http %s %s: %s" % (method, e.code, body[:120]))
            time.sleep(2)
        except Exception as e:
            last = str(e)[:120]
            log("tg exc %s: %s" % (method, last))
            time.sleep(3)
    log("tg give-up %s (%s)" % (method, last[:80]))
    return None


def tg_file(path, tries=4, **params):
    """sendDocument (multipart). Returns result|None."""
    if FAKE:
        return _fake_tg("sendDocument", dict(params, caption=params.get("caption")))
    bound = "----agriV11"
    body = b""
    for k, v in params.items():
        if v is None:
            continue
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (bound, k, v)).encode()
    fn = os.path.basename(path)
    body += ("--%s\r\nContent-Disposition: form-data; name=\"document\"; filename=\"%s\"\r\n"
             "Content-Type: text/html\r\n\r\n" % (bound, fn)).encode()
    with open(path, "rb") as f:
        body += f.read() + ("\r\n--%s--\r\n" % bound).encode()
    last = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(API + "/sendDocument", data=body,
                                         headers={"Content-Type": "multipart/form-data; boundary=" + bound,
                                                  "User-Agent": "agri-quiz-v11"})
            r = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
            if r.get("ok"):
                return r["result"]
            desc = str(r.get("description", ""))
            last = desc
            if r.get("error_code") == 429:
                time.sleep(int((r.get("parameters") or {}).get("retry_after", 3)) + 1)
                continue
            log("file err %s" % desc[:140])
            return None
        except Exception as e:
            last = str(e)[:120]
            log("file exc %s" % last)
            time.sleep(3)
    log("file give-up (%s)" % last[:80])
    return None


_bot = {}


def bot_id():
    if "id" not in _bot:
        r = tg("getMe") or {}
        _bot["id"] = int(r.get("id") or 0)
        _bot["username"] = r.get("username") or "?"
    return _bot["id"]


def can_post(chat=None):
    """(can_post, can_pin, reason). Telegram group is admins-only, so a plain member cannot post."""
    chat = str(chat or CHAT)
    m = tg("getChatMember", chat_id=chat, user_id=bot_id()) or {}
    status = m.get("status") or "?"
    if status in ("administrator", "creator"):
        return True, bool(m.get("can_pin_messages", True) or status == "creator"), "admin"
    c = tg("getChat", chat_id=chat) or {}
    perms = c.get("permissions") or {}
    if perms.get("can_send_messages") and perms.get("can_send_polls", True):
        return True, bool(perms.get("can_pin_messages")), "member with posting rights"
    return False, False, "bot status=%s and chat is admins-only (can_send_messages=%s)" % (
        status, perms.get("can_send_messages"))


def dm_admin(text, reason="", gap=1800):
    """DM the admin chat, rate-limited per reason. Silently no-ops when ADMIN_CHAT is unset."""
    if not ADMIN_CHAT:
        log("dm_admin skipped (no ADMIN_CHAT):", reason)
        return None
    st = jload()
    dms = st.setdefault("dm", {})
    now = time.time()
    if reason and now - float(dms.get(reason, 0)) < gap:
        log("dm_admin throttled:", reason)
        return None
    r = tg("sendMessage", chat_id=ADMIN_CHAT, text=text, disable_web_page_preview=True)
    if r:
        dms[reason] = now
        st["dm"] = dms
        jsave(st, "dm:%s" % (reason or "alert"))
    return r


# --------------------------------------------------------------------------- journal (state.json in git)
_S = {"st": None, "sha": None}


def gh(path, method="GET", body=None, timeout=30):
    req = urllib.request.Request(GH_API + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method,
                                 headers={"Authorization": "Bearer " + GH_TOKEN,
                                          "Content-Type": "application/json",
                                          "User-Agent": "agri-quiz-v11",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else {}


def jload(force=False):
    """Read state.json. Contents API for normal sizes; blobs API once the journal passes 1 MB
    (the contents API silently returns no body for those, which would otherwise kill the journal)."""
    if _S["st"] is not None and not force:
        return _S["st"]
    st, sha = {}, None
    if GH_TOKEN and not FAKE:
        try:
            d = gh("/contents/state.json")
            sha = d.get("sha")
            if d.get("content"):
                st = json.loads(base64.b64decode(d["content"]).decode())
            elif sha:
                log("journal >1MB -> reading via blobs API")
                blob = gh("/git/blobs/" + sha, timeout=60)
                st = json.loads(base64.b64decode(blob["content"]).decode())
        except Exception as e:
            log("journal remote load failed (%s) -> local copy" % str(e)[:60])
    if st == {}:
        try:
            st = json.load(open(STATE))
        except Exception:
            st = {}
    st.setdefault("days", {})
    st.setdefault("booksend", {})
    st.setdefault("version", VERSION)
    _S["st"], _S["sha"] = st, sha
    return st


def _merge_job(a, b):
    if not a:
        return b or {}
    if not b:
        return a
    ka = (int(a.get("step", 0)), int(a.get("qidx", 0)))
    kb = (int(b.get("step", 0)), int(b.get("qidx", 0)))
    win, lose = (a, b) if ka >= kb else (b, a)
    out = dict(lose)
    out.update(win)
    for k in ("done_at", "sealed", "missed", "killed", "closed"):
        if k in lose and k not in out:
            out[k] = lose[k]
    return out


def _merge_state(mine, theirs):
    """Two runners pushing state.json -> merge by max(step,qidx) per day/job (SPEC §7)."""
    out = dict(theirs)
    out.update({k: v for k, v in mine.items() if k not in ("days", "afo18", "booksend")})
    days = {}
    mdays, tdays = (mine.get("days") or {}), (theirs.get("days") or {})
    for day in set(mdays) | set(tdays):
        m, t = mdays.get(day) or {}, tdays.get(day) or {}
        days[day] = {job: _merge_job(m.get(job), t.get(job)) for job in set(m) | set(t)}
    out["days"] = days
    out["afo18"] = _merge_job(mine.get("afo18"), theirs.get("afo18"))
    bm, bt = (mine.get("booksend") or {}), (theirs.get("booksend") or {})
    out["booksend"] = bm if len(bm.get("sent") or []) >= len(bt.get("sent") or []) else bt
    return out


def jsave(st=None, note=""):
    """Write state.json + push to main with rebase-retry (409 -> re-fetch -> re-merge). Never raises."""
    st = st if st is not None else jload()
    _S["st"] = st
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=0, sort_keys=True)
            f.write("\n")
    except Exception as e:
        log("journal local write failed:", str(e)[:80])
    if not GH_TOKEN or FAKE:
        return True
    for attempt in range(6):
        try:
            raw = json.dumps(st, indent=0, sort_keys=True).encode()
            msg = "%s%s" % (VERSION, ": " + note if note else ": journal")
            if len(raw) > 700000:
                _S["sha"] = _push_via_git_data(st, raw, msg)
                return True
            payload = {"content": base64.b64encode(raw).decode(), "message": msg}
            if _S["sha"]:
                payload["sha"] = _S["sha"]
            r = gh("/contents/state.json", method="PUT", body=payload)
            _S["sha"] = (r.get("content") or {}).get("sha")
            return True
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                e.read()
            except Exception:
                pass
            if code in (409, 422, 404):
                log("journal push conflict (%s) -> rebase+merge attempt %d" % (code, attempt + 1))
                theirs, sha = {}, None
                try:
                    req = urllib.request.Request(GH_API + "/contents/state.json",
                                                 headers={"Authorization": "Bearer " + GH_TOKEN,
                                                          "User-Agent": "agri-quiz-v11"})
                    d = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
                    theirs, sha = json.loads(base64.b64decode(d["content"]).decode()), d.get("sha")
                except Exception:
                    pass
                st = _merge_state(st, theirs)
                _S["st"] = st
                _S["sha"] = sha
                time.sleep(1.5 * (attempt + 1))
                continue
            log("journal push failed HTTP %s" % code)
            return False
        except Exception as e:
            log("journal push failed:", str(e)[:90])
            time.sleep(2)
    return False


def _push_via_git_data(st, raw, msg):
    """Big-journal push: blob -> tree (base_tree = main's tree) -> commit -> ref update."""
    ref = gh("/git/ref/heads/main")
    head = ref["object"]["sha"]
    base_tree = gh("/git/commits/" + head)["tree"]["sha"]
    blob = gh("/git/blobs", method="POST", body={"content": base64.b64encode(raw).decode(),
                                                 "encoding": "base64"}, timeout=90)["sha"]
    tree = gh("/git/trees", method="POST", body={"base_tree": base_tree, "tree": [
        {"path": "state.json", "mode": "100644", "type": "blob", "sha": blob}]}, timeout=60)["sha"]
    commit = gh("/git/commits", method="POST", body={"message": msg, "tree": tree, "parents": [head]},
                timeout=60)["sha"]
    gh("/git/refs/heads/main", method="PATCH", body={"sha": commit, "force": False})
    log("journal pushed via git-data API (%d bytes, commit %s)" % (len(raw), commit[:8]))
    return blob


def job_j(st, day=None, job=None):
    day = day or daykey()
    d = st.setdefault("days", {}).setdefault(day, {})
    j = d.setdefault(job, {})
    j.setdefault("step", 0)
    j.setdefault("qidx", 0)
    j.setdefault("ans", {})
    j.setdefault("names", {})
    return j


def sync_afo18(st, day=None):
    """state.json keeps a top-level afo18 mirror of the current day's afo entry (SPEC §6/§8).
    Never wipes the mirror when today has no afo entry yet."""
    day = day or daykey()
    a = ((st.get("days") or {}).get(day) or {}).get("afo")
    if isinstance(a, dict) and a:
        st["afo18"] = a
    return st.get("afo18") or {}


# --------------------------------------------------------------------------- sheets (read-only)
_CSV_CACHE = {}


def sheet_url(key):
    """Accept a logical key (iari / malwa_vol1 / ...) or a raw spreadsheet id."""
    return "https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:csv" % SHEETS.get(key, key)


def sheet_csv(key, tries=3):
    """Read-only CSV export. ALWAYS follows redirects (urllib does it for GET) — plain no-follow
    fetches fail, which is exactly the trap this reader exists to avoid."""
    if key in _CSV_CACHE:
        return _CSV_CACHE[key]
    if FAKE and FAKE_SHEETS:
        txt = open(os.path.join(FAKE_SHEETS, key + ".csv"), encoding="utf-8").read()
        _CSV_CACHE[key] = txt
        return txt
    url = sheet_url(key)
    last = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (agri-quiz-v11)"})
            with urllib.request.urlopen(req, timeout=60) as r:   # urllib follows the 302 for us
                txt = r.read().decode("utf-8", "replace")
            if "Serial No" in txt.split("\n")[0] or len(txt) > 200:
                _CSV_CACHE[key] = txt
                return txt
            last = "unexpected csv head"
        except Exception as e:
            last = str(e)[:100]
        time.sleep(2 + 2 * i)
    raise EngineError("sheet %s fetch failed: %s" % (key, last))


def _page_num(v):
    m = re.findall(r"\d+", str(v or ""))
    return int(m[0]) if m else 0


def _page_max(v):
    m = re.findall(r"\d+", str(v or ""))
    return int(m[-1]) if m else 0


def fit_options(opts, key_idx):
    """Telegram poll limits: option <=100 chars, 2-10 options.
    Long options are truncated; if two options become identical they get an option-letter tag so
    every option stays distinguishable (the exam keeps all 5 choices instead of dropping the row)."""
    out, trunc = [], 0
    for o in opts:
        o = " ".join(str(o).split())
        if len(o) > 100:
            o = o[:99].rstrip() + "…"
            trunc += 1
        out.append(o)
    seen = set()
    for i, o in enumerate(out):
        if o in seen:
            tag = " [%s]" % chr(65 + i)
            out[i] = (o[:100 - len(tag)]).rstrip() + tag
            trunc += 1
        seen.add(out[i])
    if len(set(out)) != len(out) or not (0 <= key_idx < len(out)):
        return out, trunc, False
    return out, trunc, True


def fit_question(text, limit=292):
    """Telegram poll question limit is 300 incl. the '25/50. ' prefix -> keep 292 + ellipsis."""
    t = " ".join(str(text or "").split())
    return (t, 0) if len(t) <= limit else (t[:limit - 1].rstrip() + "…", 1)


def sheet_rows(sid):
    """Valid rows only: question + >=2 non-empty options + key A-E inside the option range."""
    txt = sheet_csv(sid)
    rows = list(csv.reader(io.StringIO(txt)))
    if not rows:
        return []
    hdr = [h.strip().lower() for h in rows[0]]
    if "question" in " ".join(hdr):
        rows = rows[1:]
    out = []
    for n, r in enumerate(rows):
        if not any(str(c).strip() for c in r):
            continue
        r = list(r) + [""] * (len(SHEET_HEADERS) - len(r))
        q = " ".join(str(r[3]).split())
        if not q:
            continue
        opts = [" ".join(str(r[i]).split()) for i in range(4, 9)]
        opts = [o for o in opts if o]
        if len(opts) < 2:
            continue
        k = str(r[9]).strip().upper()
        if len(k) != 1 or k not in "ABCDE":
            continue
        ki = ord(k) - 65
        if ki >= len(opts):
            continue
        out.append({"serial": str(r[0]).strip(), "page": str(r[1]).strip(), "topic": str(r[2]).strip(),
                    "q": q, "opts": opts, "key": ki, "src_row": n})
    return out


# --------------------------------------------------------------------------- prebuild (freeze the day's paper)
def _take_questions(rows, start, count, used_pages=None):
    picked, skips = [], []
    i = start
    while i < len(rows) and len(picked) < count:
        r = rows[i]
        if used_pages is not None and _page_num(r["page"]) not in used_pages:
            break
        opts, trunc, ok = fit_options(r["opts"], r["key"])
        qt, qtr = fit_question(r["q"])
        if ok:
            picked.append({"uid": "%s:%s" % (r["page"], r["serial"]), "serial": r["serial"], "page": r["page"],
                           "topic": r["topic"], "q": qt, "o": opts, "key": r["key"], "trunc": trunc + qtr,
                           "src_row": r["src_row"]})
        else:
            skips.append({"src_row": r["src_row"], "serial": r["serial"], "why": "option-limit collision"})
        i += 1
    return picked, i, skips


def plan_malwa(day, j):
    """20 Q/day from the current volume; batch bookkeeping = 150 rows; volume exhausted -> next volume next day."""
    vol = int(j.get("vol", 0))
    bidx = int(j.get("bidx", 0))
    skips, rolled = [], False
    while True:
        if vol >= len(VOLUMES):
            return None, skips, "series_complete"
        sid, name = VOLUMES[vol]
        rows = sheet_rows(sid)
        if bidx < len(rows):
            break
        vol, bidx, rolled = vol + 1, 0, True
    picked, nxt, skips = _take_questions(rows, bidx, JOBS["malwa"]["n"])
    if not picked:
        return None, skips, "empty_source"
    pr = [_page_num(p["page"]) for p in picked if _page_num(p["page"])]
    pmax = max([_page_max(p["page"]) for p in picked] or [0])
    plan = {"src": sid, "kind": "sheet", "n": len(picked), "label": name, "vol": vol, "vol_index": vol,
            "batch": bidx // JOBS["malwa"]["batch"] + 1, "row_from": bidx, "row_to": nxt,
            "bidx_next": nxt, "rolled": rolled,
            "pages": ("Book pages %d-%d" % (min(pr), pmax)) if pr else "",
            "questions": picked, "trunc": sum(p["trunc"] for p in picked), "skip_rows": skips,
            "built_at": istnow().isoformat(timespec="seconds")}
    return plan, skips, None


def plan_iari(day, j):
    """All questions of the next 5 book pages, strict page order (N = actual count)."""
    sid = JOBS["iari"]["sid"]
    rows = sheet_rows(sid)
    bidx = int(j.get("bidx", 0))
    if bidx >= len(rows):
        return None, [], "series_complete"
    pages = []
    i = bidx
    while i < len(rows) and len(pages) < JOBS["iari"]["pages_per_day"]:
        pnum = _page_num(rows[i]["page"])
        if not pages or pages[-1] != pnum:
            if pnum not in pages:
                pages.append(pnum)
        i += 1
    if not pages:
        pages = [_page_num(rows[bidx]["page"])]
    picked, nxt, skips = _take_questions(rows, bidx, len(rows) - bidx, used_pages=set(pages))
    if not picked:
        return None, skips, "empty_source"
    plan = {"src": sid, "kind": "sheet", "n": len(picked), "label": JOBS["iari"]["label"],
            "pages_list": pages, "pages": "Pages %d-%d" % (pages[0], pages[-1]),
            "row_from": bidx, "row_to": nxt, "bidx_next": nxt,
            "questions": picked, "trunc": sum(p["trunc"] for p in picked), "skip_rows": skips,
            "built_at": istnow().isoformat(timespec="seconds")}
    return plan, skips, None


def plan_afo(day, j):
    """50Q full-length from the Mongo bank (set for exactly this IST day)."""
    import afo_mongo
    db, flush = afo_mongo.db_handle()
    doc = db.afo_sets.find_one({"date": day}) or {}
    qs = afo_mongo.pick(day, db=db, flush=flush)
    picked = []
    for q in qs:
        opts, trunc, ok = fit_options([str(o) for o in (q.get("o") or [])], int(q.get("key") or 0))
        if not ok:
            raise EngineError("mongo set %s has an unusable question (uid=%s)" % (day, q.get("uid")))
        qt, qtr = fit_question(q.get("q"))
        picked.append({"uid": q.get("uid"), "serial": q.get("uid"), "page": "", "topic": "",
                       "q": qt, "o": opts, "key": int(q["key"]), "trunc": trunc + qtr, "src_row": None})
    plan = {"src": "mongo:agri.afo_sets", "kind": "mongo", "n": len(picked), "label": JOBS["afo"]["label"],
            "set_no": doc.get("set_no"), "pages": "AFO full-length set (new pattern)",
            "questions": picked, "trunc": sum(p["trunc"] for p in picked), "skip_rows": [],
            "built_at": istnow().isoformat(timespec="seconds")}
    return plan, [], None


def prebuild(job, day=None, st=None):
    """Read the source and FREEZE the day's paper into the journal. Posts nothing."""
    st = st if st is not None else jload()
    day = day or daykey()
    j = job_j(st, day, job)
    if j.get("plan"):
        log("prebuild %s %s: already frozen (n=%s)" % (job, day, j["plan"].get("n")))
        return j["plan"]
    if os.environ.get("ENGINE_FAKE_FAIL") == job:
        raise EngineError("injected failure for %s (fake-clock case)" % job)
    if job == "malwa":
        plan, skips, why = plan_malwa(day, j)
    elif job == "iari":
        plan, skips, why = plan_iari(day, j)
    elif job == "afo":
        plan, skips, why = plan_afo(day, j)
    else:
        raise EngineError("unknown job " + job)
    if plan is None:
        if why == "series_complete" and not j.get("series_posted"):
            lab = {"malwa": "MALWA BOOK SERIES", "iari": "IARI BOOK MCQ 2026"}.get(job, job.upper())
            m = tg("sendMessage", chat_id=CHAT, parse_mode="HTML", disable_web_page_preview=True, text=(
                "🎊 <b>%s COMPLETE</b> — poori series khatam! Sabhi players ko shukriya 🌾\n"
                "Aaj se ye slot band. Naya series jald hi! 🔔" % esc(lab)))
            if m:
                tg("pinChatMessage", chat_id=CHAT, message_id=m["message_id"])
                j["series_posted"] = m["message_id"]
        j["step"] = 8
        j["closed"] = why or "no_plan"
        j["done_at"] = istnow().isoformat(timespec="seconds")
        j["bidx"] = j.get("bidx_next", j.get("bidx", 0))
        jsave(st, "%s closed (%s)" % (job, why))
        log("prebuild %s: no questions left -> closed (%s)" % (job, why))
        return None
    for k in ("bidx", "vol", "pages_done"):
        if k in plan:
            j[k] = plan[k]
    if plan.get("bidx_next") is not None:
        j["bidx"] = plan["bidx_next"]
    if "vol" in plan:
        j["vol"] = plan["vol"]
    j["plan"] = plan
    j["skips"] = plan.get("skip_rows") or []
    j["step"] = max(int(j.get("step", 0)), 0)
    jsave(st, "%s prebuild n=%d" % (job, plan["n"]))
    log("prebuild %s %s: n=%d vol/pages=%s trunc=%d skips=%d" % (
        job, day, plan["n"], plan.get("label") if plan.get("kind") != "sheet" else plan.get("pages"),
        plan.get("trunc", 0), len(plan.get("skip_rows") or [])))
    return plan


# --------------------------------------------------------------------------- exam flow
def announce_text(job, day, plan):
    cfg = JOBS[job]
    return "\n".join([
        "%s <b>%s</b>" % (cfg["emoji"], esc(plan.get("label") or cfg.get("label") or job.upper())),
        "📅 %s · ⏰ %s" % (day_label(day), cfg["time_label"]),
        "📝 %s questions · 30s each · ek answer, poll auto-close" % plan["n"],
        "🏆 +%s right · %s wrong · end me leaderboard + result file 📄"
        % (fmt_num(cfg["right"]), ("−" + fmt_num(abs(float(cfg["wrong"])))) if cfg["wrong"] < 0
           else fmt_num(cfg["wrong"])),
    ])


def countdown_text(job, day, plan, secs):
    cfg = JOBS[job]
    return "\n".join([
        "%s <b>%s</b>" % (cfg["emoji"], esc(plan.get("label") or cfg.get("label") or job.upper())),
        "📅 %s · ⏰ %s" % (day_label(day), cfg["time_label"]),
        "📝 %s questions · 30s each" % plan["n"],
        "⏳ <b>START in %ds…</b>" % max(0, int(secs)),
    ])


def cta_text():
    return "🌾 Roz ka schedule: 11:00 AM Malwa Book · 2:30 PM IARI Book · 6:00 PM AFO Mains — @agriquizworld"


def congrats_text(job, day, plan, rows):
    label = plan.get("label") or job.upper()
    top = ("\n🥇 Topper: <b>%s</b> — %+.1f" % (esc(rows[0]["name"]), rows[0]["score"])) if rows else ""
    tail = "" if rows else "\nAbhi koi answer nahi aaya — kal phir milte hain! 👀"
    return ("🎉 <b>%s complete</b> — %s sawal, sabko dhanyavaad! 🌾%s%s"
            % (esc(label), plan["n"], top, tail))


def _name_of(u):
    return (u.get("username") or u.get("first_name") or ("player%s" % u.get("id")))[:32]


def base_offset():
    """Start cursor for the drain. offset=-1 does NOT consume updates (verified), so use it to peek."""
    r = tg("getUpdates", offset=-1, timeout=0)
    try:
        if isinstance(r, list) and r:
            return int(r[-1]["update_id"]) + 1
        if isinstance(r, dict) and r.get("result"):
            return int(r["result"][-1]["update_id"]) + 1
    except Exception:
        pass
    return 0


def drain(off, poll_id, seconds, answers_q, names, hard_deadline):
    """Single-poller getUpdates drain; collects poll_answer for the given poll only.
    Offline (FAKE) mode does exactly one call so a poll costs 0 seconds."""
    end = time.time() + seconds
    while True:
        if not FAKE and (time.time() >= end or time.time() >= hard_deadline):
            break
        r = tg("getUpdates", offset=off, timeout=1)
        res = r if isinstance(r, list) else (r or {}).get("result")
        for u in res or []:
            off = max(off, int(u.get("update_id", 0)) + 1)
            pa = u.get("poll_answer")
            if not pa or (poll_id and pa.get("poll_id") != poll_id):
                continue
            uid = str((pa.get("user") or {}).get("id"))
            names[uid] = _name_of(pa.get("user") or {})
            oids = pa.get("option_ids") or []
            if oids:
                answers_q[uid] = int(oids[0])     # last answer per user per question wins
            else:
                answers_q.pop(uid, None)
        if FAKE:
            break
    return off


def score_rows(day, job, plan, ans, names):
    cfg = JOBS[job]
    N = plan["n"]
    stats = {}
    for i, q in enumerate(plan["questions"]):
        for uid, opt in (ans.get(str(i)) or {}).items():
            s = stats.setdefault(uid, {"right": 0, "wrong": 0})
            if opt is None:
                continue
            if int(opt) == int(q["key"]):
                s["right"] += 1
            else:
                s["wrong"] += 1
    rows = []
    for uid, s in stats.items():
        score = s["right"] * cfg["right"] + s["wrong"] * cfg["wrong"]
        rows.append({"uid": uid, "name": names.get(uid, "player%s" % uid), "score": round(score, 2),
                     "right": s["right"], "wrong": s["wrong"], "skip": max(0, N - s["right"] - s["wrong"])})
    rows.sort(key=lambda r: (-r["score"], -r["right"], r["name"].lower()))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def leaderboard_text(day, job, plan, rows, part=0):
    cfg = JOBS[job]
    label = plan.get("label") or job.upper()
    head = ("🏆 <b>%s — LEADERBOARD</b> (%dQ · %s)" % (esc(label), plan["n"], fmt_pair(cfg["right"], cfg["wrong"]))
            if part == 0 else "🏆 <b>%s</b> — leaderboard contd…" % esc(label))
    if not rows:
        return head + "\n\nAbhi koi score nahi — kal phir milte hain! 👀"
    out = [head, ""]
    for r in rows:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"]) or ("#%d." % r["rank"])
        out.append("%s <a href=\"tg://user?id=%s\">%s</a> — <b>%+.1f</b> (%d✓ %d✗)"
                   % (medal, esc(r["uid"]), esc(r["name"]), r["score"], r["right"], r["wrong"]))
    return "\n".join(out)


def result_data(day, job, plan, rows, ans):
    cfg = JOBS[job]
    keys = []
    for i, q in enumerate(plan["questions"]):
        picked = sorted({int(v) for v in ((ans.get(str(i)) or {})).values() if v is not None})
        keys.append({"n": i + 1, "q": q["q"], "opts": q["o"], "ans_idx": int(q["key"]),
                     "ans": "%s. %s" % (chr(65 + int(q["key"])), q["o"][int(q["key"])]),
                     "picked": picked})
    return {"title": "%s · DAILY TEST RESULT" % (plan.get("label") or job.upper()),
            "label": plan.get("label") or job.upper(), "date": day, "day_label": day_label(day),
            "time": cfg["time_label"], "nq": plan["n"],
            "right": fmt_num(cfg["right"]), "wrong": ("−" + fmt_num(abs(float(cfg["wrong"]))))
            if cfg["wrong"] < 0 else fmt_num(cfg["wrong"]),
            "pages": plan.get("pages") or "", "batch": ("Batch %s" % plan["batch"]) if plan.get("batch") else "",
            "rows": rows, "key": keys,
            "note": ("Source: %s · truncation applied on %d option(s) · skipped rows: %d"
                     % (plan.get("src"), plan.get("trunc", 0), len(plan.get("skip_rows") or []))),
            "book": plan.get("label") or job.upper(), "brand": "@Arunkatyanquiz_bot", "author": "AGRI QUIZ WORLD"}


def run_job(job, day=None, st=None, force=False):
    """announce -> countdown -> polls -> leaderboard -> congrats -> result file -> CTA. Resumable."""
    import builder
    st = st if st is not None else jload()
    day = day or daykey()
    j = job_j(st, day, job)
    cfg = JOBS[job]
    plan = j.get("plan") or prebuild(job, day, st)
    if not plan:
        log("run_job %s: nothing to run (closed)" % job)
        return "closed"
    chat = CHAT
    t_start = time.time()
    # one holder per job: another run holding a fresh heartbeat wins (SPEC §6 lock rule)
    if j.get("locked_by") and j["locked_by"] != RUN_ID and time.time() - float(j.get("lock_ts", 0)) < 120:
        log("run_job %s: locked by run %s -> skip" % (job, j["locked_by"]))
        return "locked"
    j["locked_by"] = RUN_ID
    j["lock_ts"] = time.time()
    jsave(st, "%s lock" % job)
    log("run_job %s %s n=%d step=%s qidx=%s" % (job, day, plan["n"], j.get("step"), j.get("qidx")))

    # --- step 1: announce once (pinned)
    if int(j.get("step", 0)) < 1:
        m = tg("sendMessage", chat_id=chat, text=announce_text(job, day, plan), parse_mode="HTML",
               disable_web_page_preview=True)
        if not m:
            raise EngineError("announce failed for %s (check bot admin rights)" % job)
        j["msg_ann"] = m["message_id"]
        j["announced_at"] = istnow().isoformat(timespec="seconds")
        j["step"] = 1
        p = tg("pinChatMessage", chat_id=chat, message_id=m["message_id"])
        j["pinned_ann"] = bool(p)
        if not p:
            dm_admin("⚠️ %s announce pin nahi ho paya (bot ko pin rights do)." % job, "pin:" + job, 6 * 3600)
        jsave(st, "%s announce #%s" % (job, j["msg_ann"]))
        log("announce %s msg=%s pinned=%s" % (job, j["msg_ann"], bool(p)))

    # --- countdown to go (only when polls have not started and we are early)
    if int(j.get("step", 0)) < 2:
        go = go_dt(day, job)
        last_edit, last_push = 0.0, time.time()
        while True:
            d2g = (go - istnow()).total_seconds()
            if d2g <= 0:
                break
            if time.time() - t_start > CD_MAX:
                log("countdown %s: budget out, starting now" % job)
                break
            if j.get("msg_ann") and d2g <= 61 and (time.time() - last_edit) >= 10:
                tg("editMessageText", chat_id=chat, message_id=j["msg_ann"], parse_mode="HTML",
                   text=countdown_text(job, day, plan, int(d2g)))
                last_edit = time.time()
            if time.time() - last_push > 100:
                j["lock_ts"] = time.time()
                j["locked_by"] = RUN_ID
                jsave(st, "%s heartbeat" % job)
                last_push = time.time()
            sleep(min(d2g, 8 if d2g > 61 else 2))
        j["step"] = 2
        j["started_at"] = istnow().isoformat(timespec="seconds")
        jsave(st, "%s polls start" % job)

    # --- polls (one open at a time, live scoring, journal every 5Q / 100s)
    N = plan["n"]
    ans = j.setdefault("ans", {})
    names = j.setdefault("names", {})
    resume_at = max(int(j.get("qidx", 0)), int(j.get("sent_i", -1)) + 1)
    if resume_at > 0:
        log("resume %s at Q%d (qidx=%s sent_i=%s)" % (job, resume_at + 1, j.get("qidx"), j.get("sent_i")))
    off = base_offset()
    hard = time.time() + TEST_BUDGET
    fails = 0
    last_push = time.time()
    for i in range(resume_at, N):
        if time.time() > hard:
            j["partial"] = True
            log("poll budget exhausted at Q%d" % (i + 1))
            break
        q = plan["questions"][i]
        j["sent_i"] = i                       # written BEFORE sendPoll -> resume never duplicates a question
        j["lock_ts"] = time.time()
        j["locked_by"] = RUN_ID
        jsave(st, "%s poll %d claim" % (job, i + 1))
        poll = tg("sendPoll", chat_id=chat, question="%d/%d. %s" % (i + 1, N, esc(q["q"])), options=q["o"],
                  type="regular", is_anonymous=False, allows_multiple_answers=False,
                  open_period=POLL_SECONDS, parse_mode="HTML")
        pid = ((poll or {}).get("poll") or {}).get("id")
        if not pid:
            fails += 1
            log("sendPoll failed for Q%d (fail %d/3)" % (i + 1, fails))
            if fails >= 3:
                j["partial"] = True
                log("3 consecutive poll failures -> closing test early")
                break
            continue
        fails = 0
        j.setdefault("poll_ids", {})[str(i)] = pid
        aq = ans.setdefault(str(i), {})
        off = drain(off, pid, POLL_SECONDS + 1.5, aq, names, hard)
        j["qidx"] = i + 1
        j["step"] = 2
        j["lock_ts"] = time.time()
        if (i + 1) % 5 == 0 or i + 1 == N or time.time() - last_push > 100:
            jsave(st, "%s polls %d" % (job, i + 1))
            last_push = time.time()
    j["step"] = max(int(j.get("step", 0)), 3)
    j["polled"] = int(j.get("qidx", 0))
    jsave(st, "%s polls done" % job)

    # --- leaderboard (48 rows/msg)
    rows = score_rows(day, job, plan, ans, names)
    if not j.get("lb_sent"):
        for part, i in enumerate(range(0, max(len(rows), 1), LB_ROWS)):
            txt = leaderboard_text(day, job, plan, rows[i:i + LB_ROWS], part)
            tg("sendMessage", chat_id=chat, text=txt[:4000], parse_mode="HTML", disable_web_page_preview=True)
        j["lb_sent"] = True
        j["step"] = 4
        j["players"] = len(rows)
        j["answered_total"] = sum(len(v) for v in ans.values())
        jsave(st, "%s leaderboard" % job)

    # --- congrats (pinned)
    if not j.get("congrats_sent"):
        c = tg("sendMessage", chat_id=chat, text=congrats_text(job, day, plan, rows), parse_mode="HTML",
               disable_web_page_preview=True)
        if c:
            tg("pinChatMessage", chat_id=chat, message_id=c["message_id"])
            j["congrats_sent"] = c["message_id"]
            jsave(st, "%s congrats" % job)

    # --- result file (6065 HTML, UNPINNED) + one short CTA
    if not j.get("file_sent"):
        slug = re.sub(r"[^A-Z0-9]+", "_", (plan.get("label") or job).upper()).strip("_")
        path = os.path.join(OUTDIR, "%s_%s_results.html" % (slug, day))
        builder.render_html(result_data(day, job, plan, rows, ans), 0, plan.get("label") or job.upper(),
                            "AGRI QUIZ WORLD", "@Arunkatyanquiz_bot", LB_ROWS, True, path)
        doc = tg_file(path, chat_id=chat, caption="📄 %s — %s · %dQ scores + answer key"
                      % (plan.get("label") or job.upper(), day_label(day), plan["n"]))
        if doc:
            j["file_sent"] = os.path.basename(path)
            j["file_msg"] = doc.get("message_id")
            jsave(st, "%s result file" % job)
        else:
            log("result file send failed (will retry next cycle)")
    if not j.get("cta_sent"):
        c = tg("sendMessage", chat_id=chat, text=cta_text(), parse_mode="HTML", disable_web_page_preview=True)
        if c:
            j["cta_sent"] = c["message_id"]
    j["step"] = 8
    j["done_at"] = istnow().isoformat(timespec="seconds")
    j["elapsed_s"] = int(time.time() - t_start)
    j["partial"] = bool(j.get("partial"))
    j["locked_by"] = ""
    jsave(st, "%s complete" % job)
    if job == "afo":
        try:
            import afo_mongo
            n = afo_mongo.mark(day)
            log("mongo %s marked used (%d uids booked)" % (day, n))
        except Exception as e:
            log("mongo mark failed:", str(e)[:100])
    log("DONE %s %s players=%d" % (job, day, len(rows)))
    return "done"


# --------------------------------------------------------------------------- scheduler
def job_state(st, day, job):
    return ((st.get("days") or {}).get(day) or {}).get(job) or {}


def is_closed(job, day):
    cfg = JOBS[job]
    if cfg.get("last_day") and day > cfg["last_day"]:
        return "schedule_end"
    return None


def slot_phase(job, day, j):
    """idle | wait | warm | late | missed | done | closed"""
    if int(j.get("step", 0)) >= 8:
        return "done"
    c = is_closed(job, day)
    if c:
        return "closed"
    go = go_dt(day, job)
    d2g = (go - istnow()).total_seconds()
    if d2g > WINDOW_BEFORE:
        return "idle"
    if -WINDOW_AFTER <= d2g <= WINDOW_BEFORE:
        return "warm" if d2g > 0 else "late"
    if d2g < -WINDOW_AFTER:
        return "missed"
    return "idle"


def actionable_jobs(st, day):
    out = []
    for job in ORDER:
        j = job_state(st, day, job)
        ph = slot_phase(job, day, j)
        if ph in ("warm", "late"):
            out.append(job)
    return out


def cycle_job(st, day, job):
    j = job_j(st, day, job)
    ph = slot_phase(job, day, j)
    log("cycle %s %s: phase=%s step=%s" % (job, day, ph, j.get("step")))
    if ph == "done":
        return "done"
    if ph == "closed":
        if not j.get("closed"):
            j["step"] = 8
            j["closed"] = is_closed(job, day)
            j["done_at"] = istnow().isoformat(timespec="seconds")
            jsave(st, "%s closed (%s)" % (job, j["closed"]))
        return "closed"
    if ph == "missed":
        if not j.get("missed"):
            j["step"] = 8
            j["missed"] = True
            j["done_at"] = istnow().isoformat(timespec="seconds")
            jsave(st, "%s missed (window passed)" % job)
            if job == "afo":
                try:
                    import afo_mongo
                    db, flush = afo_mongo.db_handle()
                    doc = db.afo_sets.find_one({"date": day}) or {}
                    if doc.get("status") == "running":
                        db.afo_sets.update_one({"date": day}, {"$set": {
                            "status": "ready", "note": "slot missed — set unused (never retro-fired)"}})
                        flush()
                        log("mongo: %s released back to ready (unused)" % day)
                except Exception as e:
                    log("mongo release failed:", str(e)[:80])
            dm_admin("⚠️ %s slot %s IST miss ho gaya (go+4h cross) — seal kar diya, retro-fire nahi hoga."
                     % (job.upper(), JOBS[job]["time_label"]), "missed:" + job, 6 * 3600)
        return "missed"
    if ph == "idle":
        return "wait"
    # in window: rights gate first — never announce if the bot cannot post
    ok, can_pin, why = can_post(CHAT)
    if not ok:
        j["blocked"] = {"reason": why, "ts": istnow().isoformat(timespec="seconds")}
        jsave(st, "%s blocked (no rights)" % job)
        dm_admin("⛔ %s start nahi ho paya: %s\nFix: @agriquizworld → Administrators → @Arunkatyanquiz_bot "
                 "ko Post+Pin rights do." % (job.upper(), why), "blocked:" + job, 1800)
        return "blocked"
    if not j.get("plan"):
        prebuild(job, day, st)
        if job_state(st, day, job).get("closed"):
            return "closed"
    if ph == "warm":
        # wait happens inside run_job (countdown edits the pinned announce)
        pass
    return run_job(job, day, st)


def slotchain():
    st = jload()
    day = daykey()
    results = {}
    for job in ORDER:
        try:
            results[job] = cycle_job(st, day, job)
        except Exception as e:
            results[job] = "error"
            log("ERROR job %s isolated: %s" % (job, str(e)[:160]))
            try:
                j = job_j(st, day, job)
                j["last_error"] = {"msg": str(e)[:200], "at": istnow().isoformat(timespec="seconds")}
                jsave(st, "%s error" % job)
            except Exception:
                pass
            dm_admin("❗️%s cycle error: %s" % (job.upper(), str(e)[:200]), "error:" + job, 3600)
    sync_afo18(st, day)
    jsave(st, "cycle %s" % ",".join("%s=%s" % (k, v) for k, v in results.items()))
    log("cycle done:", results)
    return results


def dispatch(wf, inputs=None):
    """workflow_dispatch with the runner token. workflow_dispatch is allowed for GITHUB_TOKEN events."""
    if FAKE:
        log("dispatch(fake): %s inputs=%s" % (wf, inputs or {}))
        return "fake"
    try:
        req = urllib.request.Request(GH_API + "/actions/workflows/%s/dispatches" % wf,
                                     data=json.dumps({"ref": "main", "inputs": inputs or {}}).encode(),
                                     method="POST",
                                     headers={"Authorization": "Bearer " + GH_TOKEN,
                                              "Content-Type": "application/json",
                                              "User-Agent": "agri-quiz-v11",
                                              "Accept": "application/vnd.github+json"})
        urllib.request.urlopen(req, timeout=25)
        log("dispatch: %s dispatched" % wf)
        return "dispatched"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()[:160]
        except Exception:
            body = ""
        log("dispatch %s failed HTTP %s %s" % (wf, e.code, body))
    except Exception as e:
        log("dispatch %s failed: %s" % (wf, str(e)[:120]))
    return "failed"


def rearm(force=False):
    """slot-chain's self-chain step: only continues while a slot is still actionable today."""
    st = jload(force=True)
    day = daykey()
    todo = actionable_jobs(st, day)
    if not force and not todo:
        log("rearm: no further cycle needed today (done/sealed/closed)")
        return "idle"
    log("rearm: todo=%s (force=%s)" % (todo or "none", force))
    return dispatch("slot-chain.yml")


def _wf_runs(wf_file, statuses=("in_progress", "queued", "requested", "waiting", "pending")):
    out = []
    if FAKE or not GH_TOKEN:
        return out
    for s in statuses:
        try:
            req = urllib.request.Request("%s/actions/workflows/%s/runs?status=%s&per_page=20" % (GH_API, wf_file, s),
                                         headers={"Authorization": "Bearer " + GH_TOKEN,
                                                  "User-Agent": "agri-quiz-v11",
                                                  "Accept": "application/vnd.github+json"})
            d = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
            out += d.get("workflow_runs") or []
        except Exception as e:
            log("runs query failed (%s): %s" % (s, str(e)[:80]))
    return out


def guard():
    """Watchdog (self-chained ~7 min): revive a stale slot-chain, DM only for real work."""
    if FAKE:
        log("guard(fake): watchdog pass skipped (offline)")
        return "fake"
    st = jload(force=True)
    day = daykey()
    live = _wf_runs("slot-chain.yml")
    if live:
        log("guard: chain alive (%s)" % live[0].get("status"))
        return "alive"
    runs = _wf_runs("slot-chain.yml", ("completed",))
    stale_min = 999.0
    if runs:
        try:
            created = dt.datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00"))
            stale_min = (istnow() - created.astimezone(IST)).total_seconds() / 60.0
        except Exception:
            pass
    todo = actionable_jobs(st, day)
    log("guard: no live chain, last run %.1f min ago, actionable=%s" % (stale_min, todo))
    if todo and stale_min > 25:
        rearm(force=True)
        dm_admin("🛡 slot-guard: slot-chain %.0f min se stale tha -> revive kar diya (%s)."
                 % (stale_min, ",".join(todo)), "guard", 3600)
        return "revived"
    if todo:
        rearm(force=True)
        return "kick"
    return "idle"


def agent():
    """Maintenance pass (keepwarm job): journal sanity, blocked alerts, daily supply audit."""
    import afo_mongo
    st = jload(force=True)
    day = daykey()
    issues = []
    for d, jobs in sorted((st.get("days") or {}).items()):
        if d != day:
            continue
        for job, j in jobs.items():
            if not isinstance(j, dict):
                issues.append("%s/%s malformed" % (d, job))
                continue
            if j.get("locked_by") and int(j.get("step", 0)) in (1, 2, 3, 4) and \
                    time.time() - float(j.get("lock_ts", 0)) > 900:
                issues.append("%s/%s stale lock by %s (step %s)" % (d, job, j.get("locked_by"), j.get("step")))
            if j.get("blocked") and int(j.get("step", 0)) < 8:
                issues.append("%s/%s blocked: %s" % (d, job, (j.get("blocked") or {}).get("reason")))
    rep = {}
    if istnow().hour >= 6 and st.get("supply_day") != day:
        try:
            rep = afo_mongo.supply()
            st["supply_day"] = day
            st.setdefault("supply_log", {})[day] = {k: rep.get(k) for k in ("checked", "missing", "bad", "filled")}
            log("agent: supply audit %s" % {k: rep.get(k) for k in ("checked", "missing", "bad", "next_set_no")})
        except Exception as e:
            issues.append("supply audit failed: %s" % str(e)[:100])
    st["agent_last"] = istnow().isoformat(timespec="seconds")
    st["agent_issues"] = issues[-10:]
    jsave(st, "agent pass")
    if issues:
        log("agent issues:", " | ".join(issues[-5:]))
    return {"issues": issues, "supply": rep}


def keepwarm():
    lines = []
    if RENDER_URL and not FAKE:
        t0 = time.time()
        try:
            req = urllib.request.Request(RENDER_URL, headers={"User-Agent": "agri-quiz-v11-keepwarm"})
            with urllib.request.urlopen(req, timeout=45) as r:
                lines.append("render %s in %.1fs" % (r.status, time.time() - t0))
        except urllib.error.HTTPError as e:
            lines.append("render HTTP %s in %.1fs" % (e.code, time.time() - t0))
        except Exception as e:
            lines.append("render err %s" % str(e)[:80])
    else:
        lines.append("render ping skipped (no RENDER_URL/fake)")
    a = agent()
    log("keepwarm:", "; ".join(lines), "| agent issues=%d" % len(a.get("issues") or []))
    return lines


# --------------------------------------------------------------------------- supply / status / ready
def supply():
    import afo_mongo
    rep = afo_mongo.supply()
    print(json.dumps(rep, indent=1, default=str))
    st = jload()
    st.setdefault("supply_log", {})[daykey()] = {k: rep.get(k) for k in ("checked", "missing", "bad", "filled")}
    st["supply_day"] = daykey()
    jsave(st, "supply audit")
    return rep


def status():
    st = jload(force=True)
    day = daykey()
    print("IST now: %s | version %s | repo %s" % (istnow().strftime("%Y-%m-%d %H:%M:%S %a"), VERSION, REPO))
    print("chat_for(*) -> %s (locked) | admin dm: %s" % (CHAT, "set" if ADMIN_CHAT else "unset"))
    print("-- today %s" % day)
    for job in ORDER:
        j = job_state(st, day, job)
        print("  %-6s %-7s step=%-2s qidx=%-3s n=%-3s ann=%-6s closed=%s missed=%s" % (
            job, slot_phase(job, day, j), j.get("step", "-"), j.get("qidx", "-"),
            (j.get("plan") or {}).get("n", "-"), j.get("msg_ann", "-"),
            j.get("closed", ""), j.get("missed", "")))
    print("-- journal days:", ", ".join(sorted((st.get("days") or {}).keys())[-6:]))
    try:
        import afo_mongo
        print("-- mongo:", json.dumps(afo_mongo.status(), default=str)[:400])
    except Exception as e:
        print("-- mongo unavailable:", str(e)[:80])


def ready():
    ok, can_pin, why = can_post(CHAT)
    b = tg("getMe") or {}
    print("GATE0 chat=%s bot=@%s can_post=%s can_pin=%s reason=%s" % (CHAT, b.get("username"), ok, can_pin, why))
    return 0 if ok else 3


# --------------------------------------------------------------------------- booksend (manual dispatch only)
def quickmd(s, n=64):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def booksend(job, rng, step, chat=None):
    """One-off delivery of book MCQ files (manual dispatch only; NEVER auto-fired).
    job: chapter=page-based source key from SHEETS; rng 'a-b' in book pages; step = pages per file."""
    import builder
    a, b = [int(x) for x in str(rng).split("-")]
    step = int(step)
    chat = str(chat or CHAT)
    rows = sheet_rows(job)
    if not rows:
        raise EngineError("no rows for %s" % job)
    st = jload()
    bs = st.setdefault("booksend", {})
    key = "%s:%s:%s:%s" % (job, a, b, step)
    if bs.get("key") != key:
        bs.clear()
        bs.update({"key": key, "job": job, "chat": chat, "range": [a, b], "step": step, "sent": [], "done": False})
        jsave(st, "booksend start %s" % key)
    done_pages = {tuple(f["pages"]) for f in bs.get("sent") or []}
    by_page = {}
    for r in rows:
        by_page.setdefault(_page_num(r["page"]), []).append(r)
    pages = [p for p in range(a, b + 1) if p in by_page]
    log("booksend %s: %d pages with questions in %s" % (job, len(pages), rng))
    idx_msg = bs.get("index_msg")
    for i in range(0, len(pages), step):
        chunk = pages[i:i + step]
        if tuple(chunk) in done_pages:
            continue
        qs = [r for p in chunk for r in by_page[p]]
        DATA = {"title": "%s · BOOK MCQ" % job.upper(), "label": "%s (pages %d-%d)" % (job.upper(), chunk[0], chunk[-1]),
                "nq": len(qs), "pages": "Pages %d-%d" % (chunk[0], chunk[-1]),
                "rows": [], "key": [{"n": n + 1, "q": q["q"], "opts": q["opts"], "ans_idx": q["key"],
                                     "ans": "%s. %s" % (chr(65 + q["key"]), q["opts"][q["key"]])}
                                    for n, q in enumerate(qs)]}
        path = os.path.join(OUTDIR, "booksend/%s_%d-%d.html" % (job, chunk[0], chunk[-1]))
        builder.render_html(DATA, step, job.upper(), "AGRI QUIZ WORLD", "@MCQBYBOOK_bot", 48, True, path)
        cap = "📚 %s — pages %d-%d (%d Q) · answers included 📄" % (job.upper(), chunk[0], chunk[-1], len(qs))
        doc = tg_file(path, chat_id=chat, caption=cap)
        if not doc:
            log("booksend: send failed at pages %d-%d (resume later)" % (chunk[0], chunk[-1]))
            break
        mid = doc.get("message_id")
        tg("pinChatMessage", chat_id=chat, message_id=mid, disable_notification=True)
        bs["sent"].append({"pages": chunk, "msg_id": mid})
        jsave(st, "booksend %d-%d" % (chunk[0], chunk[-1]))
        time.sleep(1.2)
    # INDEX last + nav fix-up
    if len(bs["sent"]) == len(range(0, len(pages), step)):
        cnum = str(chat).replace("-100", "").replace("-", "")
        if not bs.get("index_msg"):
            lines = ["📚 <b>%s — INDEX</b> (pages %s · %s files)" % (job.upper(), rng, len(bs["sent"]))]
            for k, f in enumerate(bs["sent"], 1):
                lines.append("<a href=\"https://t.me/c/%s/%s\">%d. Pages %d-%d</a>"
                             % (cnum, f["msg_id"], k, f["pages"][0], f["pages"][-1]))
            m = tg("sendMessage", chat_id=chat, text="\n".join(lines)[:4000], parse_mode="HTML",
                   disable_web_page_preview=True)
            if m:
                tg("pinChatMessage", chat_id=chat, message_id=m["message_id"])
                bs["index_msg"] = m["message_id"]
                jsave(st, "booksend index")
        ix = bs.get("index_msg")
        for k, f in enumerate(bs["sent"]):
            if f.get("nav_done"):
                continue
            prev = ("<a href=\"https://t.me/c/%s/%s\">◀️ Prev</a>" % (cnum, bs["sent"][k - 1]["msg_id"])) if k else "◀️ Prev"
            nxt = ("<a href=\"https://t.me/c/%s/%s\">Next ▶️</a>" % (cnum, bs["sent"][k + 1]["msg_id"])) \
                if k + 1 < len(bs["sent"]) else "Next ▶️"
            nav = "%s | <a href=\"https://t.me/c/%s/%s\">📚 Index</a> | %s" % (prev, cnum, ix, nxt)
            tg("editMessageCaption", chat_id=chat, message_id=f["msg_id"], parse_mode="HTML",
               caption="📚 %s — pages %d-%d\n%s" % (job.upper(), f["pages"][0], f["pages"][-1], nav))
            f["nav_done"] = True
            jsave(st, "booksend nav %d" % f["msg_id"])
        bs["done"] = True
        jsave(st, "booksend done")
    log("booksend: %d/%d files sent" % (len(bs["sent"]), len(range(0, len(pages), step))))
    return bs


# --------------------------------------------------------------------------- main
def main(argv):
    cmd = argv[0] if argv else "status"
    args = argv[1:]
    if cmd == "slotchain":
        slotchain()
    elif cmd == "rearm":
        rearm(force="force" in args)
    elif cmd == "dispatch":
        dispatch(args[0])
    elif cmd == "run":
        run_job(args[0])
    elif cmd == "prebuild":
        prebuild(args[0])
    elif cmd == "status":
        status()
    elif cmd == "ready":
        return ready()
    elif cmd == "guard":
        guard()
    elif cmd == "agent":
        print(json.dumps(agent(), indent=1, default=str))
    elif cmd == "keepwarm":
        keepwarm()
    elif cmd == "supply":
        supply()
    elif cmd == "booksend":
        booksend(args[0], args[1], args[2], args[3] if len(args) > 3 else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
