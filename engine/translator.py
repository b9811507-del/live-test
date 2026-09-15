#!/usr/bin/env python3
"""translator.py — professional English language layer (v11.1).

WHY A MODULE (not scattered strings):
  * every fixed user-facing message lives here as authored, professional English (deterministic,
    works with zero network) — this is what removes Hinglish from the groups;
  * content that may arrive in Hindi/Hinglish (sheet topics, explanations, community text) is
    machine-translated through a provider chain with cache + domain glossary, so the output keeps an
    educational register ("soil fertility", not "soil fertility-ness");
  * offline / rate-limited -> the glossary and the original text are used, never a crash.

Provider chain (first success wins): Google clients5 -> Google gtx -> MyMemory -> glossary only.
Cache: json file (default out/trans_cache.json, bounded) + optional journal-backed dict.
"""
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (agri-quiz-v11; educational)"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.environ.get("TRANS_CACHE", os.path.join(ROOT, "out", "trans_cache.json"))
TIMEOUT = int(os.environ.get("TRANS_TIMEOUT", "20"))

# --------------------------------------------------------------------------- domain glossary
# Agricultural register: machine translations of these get corrected to the standard term.
GLOSSARY = {
    "crop cycle": "crop rotation",
    "soil fertility-ness": "soil fertility",
    "animal husbandry department": "Department of Animal Husbandry",
    "sugarcane premium batch": "Sugarcane Premium Batch",
    "livestock officer": "Livestock Officer",
    "agriculture science": "agricultural science",
    "agri science": "agricultural science",
    "fertiliser": "fertilizer",
    "pesticides management": "pesticide management",
    "irrigation management": "irrigation management",
}


def _polish(text):
    """Educational-register polish: clean spacing, sentence case, typographic punctuation."""
    t = " ".join(str(text or "").split())
    t = t.replace(" ,", ",").replace(" .", ".").replace(" ;", ";").replace(" ?", "?").replace(" !", "!")
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    t = re.sub(r"([,.!?;:])(?=[^\s\d])", r"\1 ", t)
    t = t.replace("--", "—")
    for k, v in GLOSSARY.items():
        t = re.sub(r"\b%s\b" % re.escape(k), v, t, flags=re.I)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def needs_translation(text):
    """True when the text is not plain ASCII English (Devanagari, Hinglish markers, other scripts)."""
    t = str(text or "")
    if not t.strip():
        return False
    if re.search(r"[\u0900-\u097F\u0980-\u0DFF\u0A00-\u0B7F]", t):     # Indic scripts
        return True
    hindi_markers = (" hai ", " hain", " kya ", " ke ", " ki ", " ka ", " me ", " ko ", " nahi",
                     " kitna", " kaun", " sahi", " jawab", " prashn", " fasal", " mitti", " doodh",
                     " pashu", " kisan", " kheti", " krishi", " beej", " khad")
    low = " " + t.lower() + " "
    hits = sum(1 for m in hindi_markers if m in low)
    return hits >= 3          # English exam text must never be rewritten by a false positive


# --------------------------------------------------------------------------- cache
_CACHE = None


def _load_cache():
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.load(open(CACHE_PATH, encoding="utf-8"))
        except Exception:
            _CACHE = {}
    return _CACHE


def _save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        c = _load_cache()
        if len(c) > 800:                                   # bounded, oldest dropped
            for k in list(c.keys())[:len(c) - 800]:
                c.pop(k, None)
        json.dump(c, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception:
        pass


def _key(text, target):
    return "%s:%s" % (target, hashlib.sha1(text.encode("utf-8")).hexdigest()[:16])


# --------------------------------------------------------------------------- providers
def _extract(x):
    """Pull the translated text out of every shape Google returns.
       [["sentence","hi"]]                      -> "sentence"      (clients5)
       [["seg 1","hi"],["seg 2","hi"]]           -> "seg 1seg 2"
       [[["seg","src","",None],["seg2",...]]]    -> "segseg2"       (gtx)
    The old parser read [["text","hi"]] as text[0]+lang[0] = "Sh" — that is the bug this fixes."""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        out = ""
        for i in x:
            if isinstance(i, list) and len(i) == 2 and isinstance(i[0], str) and isinstance(i[1], str) \
                    and len(i[1]) <= 8:
                out += i[0]
            else:
                out += _extract(i)
        return out
    return ""


def _p_clients5(text, target="en"):
    url = ("https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=auto&tl=%s&q=%s"
           % (target, urllib.parse.quote(text)))
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
        return _extract(json.loads(r.read().decode("utf-8", "replace")))


def _p_gtx(text, target="en"):
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl=%s&q=%s"
           % (target, urllib.parse.quote(text)))
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
        return _extract(json.loads(r.read().decode("utf-8", "replace"))).split("__sep__")[0]


def _p_mymemory(text, target="en"):
    url = "https://api.mymemory.translated.net/get?langpair=hi%%7C%s&q=%s" % (target, urllib.parse.quote(text))
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    out = ((d.get("responseData") or {}).get("translatedText") or "").strip()
    if out and "INVALID" not in out.upper():
        return out
    return ""


PROVIDERS = [("clients5", _p_clients5), ("gtx", _p_gtx), ("mymemory", _p_mymemory)]
_STATS = {"hits": 0, "calls": 0, "errors": 0, "provider": None}


def translate(text, target="en", use_cache=True):
    """Professional English rendering of a dynamic string. Never raises; falls back to the source."""
    src = " ".join(str(text or "").split())
    if not src:
        return ""
    if not needs_translation(src):
        return _polish(src)
    if use_cache:
        c = _load_cache()
        hit = c.get(_key(src, target))
        if hit and hit.get("out"):
            _STATS["hits"] += 1
            return hit["out"]
    out = ""
    min_ok = max(3, min(len(src) // 4, 12))          # guard against truncated/garbled provider output
    for name, fn in PROVIDERS:
        try:
            cand = fn(src, target)
            _STATS["calls"] += 1
            if cand and len(cand.strip()) >= min_ok:
                out = cand
                _STATS["provider"] = name
                break
            if cand:
                out = out or cand                     # keep as last resort, keep trying providers
        except Exception:
            _STATS["errors"] += 1
            time.sleep(0.6)
    out = _polish(out) if out else _polish(src)
    if use_cache and out:
        c = _load_cache()
        c[_key(src, target)] = {"src": src[:160], "out": out[:400], "at": int(time.time()), "p": _STATS["provider"]}
        _save_cache()
    return out


def translate_safe(text, target="en"):
    """For exam content: translate only when needed, and never let a failure change the paper."""
    try:
        return translate(text, target)
    except Exception:
        return " ".join(str(text or "").split())


def stats():
    return dict(_STATS, cached=len(_load_cache()))


# --------------------------------------------------------------------------- authored English strings
T = {
    # ---- announcements (4 lines, locked shape, professional English)
    "ann_title": "%(emoji)s %(label)s",
    "ann_when": "📅 %(date)s · ⏰ %(time)s",
    "ann_body": "📝 %(n)s questions · 30 seconds each · one answer, poll auto-closes",
    "ann_pages": "📖 Book pages: %(pages)s",
    "ann_pages_range": "📖 %(pages)s",
    "tomorrow_note": "📖 Tomorrow (%(date)s): <b>%(label)s</b> — book pages %(pages)s",
    "ann_score": "🏆 +%(right)s correct · −%(wrong)s incorrect · leaderboard & result file at the end 📄",
    "cd_line": "⏳ <b>Starting in %(n)ds…</b>",
    "cd_go": "⏳ <b>Starting now — good luck!</b>",
    # ---- leaderboard / closing
    "lb_head": "🏆 <b>%(label)s — LEADERBOARD</b> (%(n)s questions · +%(right)s / −%(wrong)s)",
    "lb_head_contd": "🏆 <b>%(label)s</b> — leaderboard continued…",
    "lb_empty": "No entries were recorded in this test. See you at the next one! 👀",
    "lb_toppers_head": "⭐ <b>Top scorers</b>",
    "reveal_correct": "✅ <b>Q%(n)s/%(total)s · Correct answer: %(ans)s</b>",
    "reveal_explain": "📖 %(text)s",
    "reveal_right": "👏 Correct (%(n)s): %(names)s",
    "reveal_wrong": "❌ Wrong (%(n)s): %(names)s",
    "reveal_none": "— no answers on this question —",
    "toppers_head": "🏆 <b>TOP 3 — %(label)s</b>",
    "toppers_row": "%(medal)s <b>%(name)s</b> — <b>%(score)s</b> · %(right)s correct · %(wrong)s wrong",
    "toppers_thanks": "🎉 %(n)s questions, %(players)s players — thank you all! 🌾",
    "toppers_none": "🎉 <b>%(label)s completed</b> — thank you all! Answer submissions were not recorded this time. See you tomorrow! 🌾",
    "schedule_head": "🗓 <b>Tomorrow's plan</b>",
    "schedule_malwa": "☀️ 11:00 AM · <b>%(label)s</b> — book pages %(pages)s",
    "schedule_iari": "🌤 2:30 PM · <b>%(label)s</b> — book pages %(pages)s",
    "schedule_afo": "🌆 6:00 PM · <b>%(label)s</b> — full-length set %(set_no)s (50 questions, +2 / −0.5)",
    "schedule_pages_unknown": "(continues automatically)",
    "lb_row_right": "correct",
    "lb_row_wrong": "incorrect",
    "congrats": ("🎉 <b>%(label)s completed</b> — %(n)s questions, thank you all for participating! 🌾\n"
                 "🥇 Top scorer: <b>%(name)s</b> — %(score)s"),
    "congrats_nobody": "🎉 <b>%(label)s completed</b> — thank you all! Answer submissions were not recorded this time. See you tomorrow! 🌾",
    "series_complete": ("🎊 <b>%(label)s COMPLETE</b> — the full series has been finished. "
                        "Thank you to every participant! 🌾\nThis slot is now closed. A new series will be announced soon."),
    "cta": "🌾 Daily schedule: 11:00 AM Malwa Book · 2:30 PM IARI Book · 6:00 PM AFO Mains — @agriquizworld",
    # ---- paid batches (last message after every test)
    "paid_title": "🎓 <b>PAID BATCHES — ENROLMENT OPEN</b>",
    "paid_intro": ("Structured courses with recorded classes, daily tests, PDF notes and full-length "
                   "mock papers. Tap a batch below to enrol."),
    "paid_row": "%(emoji)s <b>%(title)s</b> — %(price)s\n    %(perks)s",
    "paid_footer": "Payment is verified instantly and your personal one-time join link arrives in this chat.",
    "paid_btn_batch": "%(emoji)s %(title)s — Enrol %(price)s",
    "paid_btn_all": "📋 All batches & enrolment",
    "paid_empty": "🎓 <b>PAID BATCHES</b>\nEnrolment details are being updated. Please check back shortly.",
    # ---- student DM (chat box)
    "dm_welcome": ("👋 <b>Welcome to AGRI QUIZ WORLD</b>\n"
                   "Here you can enrol in a paid batch. Choose one below:"),
    "dm_batch": ("%(emoji)s <b>%(title)s</b> — %(price)s\n\n%(perks)s\n\n"
                 "1) Tap <b>Pay securely</b> and complete the payment.\n"
                 "2) Return here and tap <b>I have paid</b>.\n"
                 "3) Your personal one-time join link is sent to this chat."),
    "dm_pay_btn": "💳 Pay securely — %(price)s",
    "dm_paid_btn": "✅ I have paid",
    "dm_verify_wait": ("✅ Thank you — your enrolment for <b>%(title)s</b> is being verified.\n"
                       "Your join link will arrive in this chat within a few minutes."),
    "dm_ref_ask": "Please reply with your payment reference / UTR number so we can complete the record (optional).",
    "dm_link": ("🎉 <b>Enrolment confirmed — %(title)s</b>\n\n"
                "Your personal one-time join link:\n%(link)s\n\n"
                "This link works for one person only and expires in %(hours)s hours."),
    "dm_link_pending": ("✅ <b>Enrolment recorded for %(title)s.</b>\n"
                        "Your join link will be sent to this chat shortly by the batch team."),
    "dm_nobatch": "Please choose a batch from /start.",
    "dm_mybatches": "📚 <b>Your enrolments</b>\n%(rows)s",
    "dm_rzp_created": ("🧾 <b>Payment link ready — %(title)s</b>\n"
                       "Amount: <b>%(price)s</b> · this link is personal to you and expires in %(mins)s minutes.\n\n"
                       "1) Tap <b>Pay now</b> and complete the payment.\n"
                       "2) Your one-time join link will arrive in this chat automatically (usually within 3 minutes).\n"
                       "If you have already paid, you can also tap <b>I have paid</b>."),
    "dm_payment_received": "✅ <b>Payment received — %(title)s</b>\nThank you! Your join link is being prepared…",
    "dm_rzp_expired": ("⌛ <b>Payment link expired — %(title)s</b>\n"
                       "No problem — tap below to get a fresh payment link."),
    "dm_mybatches_none": "You have no enrolments yet. Send /start to see the available batches.",
    "dm_reissue_btn": "🔁 New join link — %(title)s",
    "dm_help": ("ℹ️ <b>How this works</b>\n"
                "• /start — view paid batches and enrol\n"
                "• /mybatches — your enrolments and a fresh join link\n"
                "• Payments are verified automatically; the join link is single-use."),
    # ---- admin DM (English)
    "adm_missed": ("⚠️ <b>%(job)s slot missed</b>\nThe scheduled start time (%(time)s IST) passed more than 4 hours ago, "
                   "so the slot has been sealed. It will not be fired retroactively."),
    "adm_blocked": ("⛔ <b>%(job)s could not start</b>\nReason: %(why)s\n"
                    "Fix: open @agriquizworld → Manage → Administrators → add @Arunkatyanquiz_bot with "
                    "Post Messages and Pin Messages rights."),
    "adm_pin": "⚠️ <b>%(job)s</b> announcement was posted but could not be pinned. Please grant Pin Messages rights.",
    "adm_error": "❗️ The <b>%(job)s</b> cycle reported an error:\n%(msg)s",
    "adm_guard": ("🛡 <b>slot-guard</b>: the scheduler chain had been stale for %(mins)s minutes — it has been revived for: %(jobs)s."),
    "adm_claim": ("💳 <b>New enrolment</b>\nBatch: %(title)s\nStudent: %(name)s (id <code>%(uid)s</code>)\n"
                  "Mode: %(mode)s\nOne-time join link issued: %(issued)s"),
    "adm_revoke": "↩️ Enrolment revoked for <code>%(uid)s</code> in %(title)s.",
    "adm_noinvite": ("⚠️ Cannot create a join link for <b>%(title)s</b>.\n"
                     "Add @Arunkatyanquiz_bot as an administrator of that batch group with the "
                     "<b>Invite Users</b> right, then the pending links will be issued on the next pass."),
    # ---- result file
    "rf_title": "%(label)s · DAILY TEST RESULT",
    "rf_caption": ("📄 <b>%(label)s</b> — pages %(pages)s (%(n)s questions) · answers & explanations "
                   "in the file · %(date)s"),
}


def t(key, **kw):
    """Authored English string (no network, deterministic). Unknown key -> the key itself, loudly."""
    s = T.get(key)
    if s is None:
        return "«missing:%s»" % key
    return s % kw if kw else s


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or "मृदा उर्वरता और फसल चक्र"
    print("in :", text)
    print("out:", translate(text))
    print("stats:", stats())
