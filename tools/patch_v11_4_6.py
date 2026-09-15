#!/usr/bin/env python3
"""v11.4.6 — (1) explanation travels WITH the poll, (2) translator covers question/options/topic.

(1) Telegram only shows an in-poll explanation on **quiz-type** polls. So every question now goes out
    as a quiz poll: correct option marked + explanation attached (200-char limit; the full text stays
    in the after-question reveal message and in the HTML paper). 30 s auto-close, non-anonymous,
    single answer — unchanged. If Telegram ever rejects the quiz form, the same poll is re-sent as a
    regular poll so a live test can never break.
(2) translator.py only translated the explanation column; question text, every option and the topic
    tag went out raw. Now all four are translated (cached) *before* the platform length limits are
    applied, so the 300-char/100-char trimming happens on the English text.
"""
import io

E = "engine/engine.py"
s = io.open(E, encoding="utf-8").read()
n0 = len(s)

# ---------------------------------------------------------------- 1. config
old = '''PAPER_BRAND = os.environ.get("PAPER_BRAND", "Agri Learning Point")      # matches the IARI group files'''
new = '''POLL_MODE = (os.environ.get("POLL_MODE", "quiz") or "quiz").strip().lower()   # quiz = explanation in the poll
POLL_EXPL_LIMIT = int(os.environ.get("POLL_EXPL_LIMIT", "200"))            # Telegram quiz explanation limit
PAPER_BRAND = os.environ.get("PAPER_BRAND", "Agri Learning Point")      # matches the IARI group files'''
assert old in s, "brand anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 2. english helper + explanation fit
old = '''def fit_options(opts, key_idx):'''
new = '''def en(text):
    """Professional English for any sheet/mongo text: translate only when it is not English already."""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    if tr.needs_translation(t):
        t = tr.translate_safe(t)
    return " ".join(str(t or "").split())


def fit_explanation(text, limit=None):
    """Telegram quiz-explanation limit (200 chars) -> trim with an ellipsis; full text stays elsewhere."""
    limit = int(limit or POLL_EXPL_LIMIT)
    t = " ".join(str(text or "").split())
    return t if len(t) <= limit else t[:limit - 1].rstrip() + "…"


def fit_options(opts, key_idx):'''
assert old in s, "fit_options anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 3. translate q / options / topic (sheets)
old = '''        opts, trunc, ok = fit_options(r["opts"], r["key"])
        qt, qtr = fit_question(r["q"])
        if ok:
            expl = r.get("expl") or ""
            if expl and tr.needs_translation(expl):
                expl = tr.translate_safe(expl)          # explanation in English (cached)
            picked.append({"uid": "%s:%s" % (r["page"], r["serial"]), "serial": r["serial"], "page": r["page"],
                           "topic": r["topic"], "q": qt, "o": opts, "key": r["key"], "trunc": trunc + qtr,
                           "expl": expl[:600], "src_row": r["src_row"]})'''
new = '''        # v11.4.6: English first, then the platform limits (question 292 / option 100 chars)
        opts, trunc, ok = fit_options([en(o) for o in r["opts"]], r["key"])
        qt, qtr = fit_question(en(r["q"]))
        if ok:
            expl, topic = en(r.get("expl") or ""), en(r.get("topic") or "")
            picked.append({"uid": "%s:%s" % (r["page"], r["serial"]), "serial": r["serial"], "page": r["page"],
                           "topic": topic, "q": qt, "o": opts, "key": r["key"], "trunc": trunc + qtr,
                           "expl": expl[:600], "src_row": r["src_row"]})'''
assert old in s, "take_questions anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 4. translate q / options / topic (mongo/AFO)
old = '''    for q in qs:
        opts, trunc, ok = fit_options([str(o) for o in (q.get("o") or [])], int(q.get("key") or 0))
        if not ok:
            raise EngineError("mongo set %s has an unusable question (uid=%s)" % (day, q.get("uid")))
        qt, qtr = fit_question(q.get("q"))
        expl = " ".join(str(q.get("expl") or "").split())
        if expl and tr.needs_translation(expl):
            expl = tr.translate_safe(expl)
        picked.append({"uid": q.get("uid"), "serial": q.get("uid"), "page": "", "topic": "",
                       "q": qt, "o": opts, "key": int(q["key"]), "trunc": trunc + qtr,
                       "expl": expl[:600], "src_row": None})'''
new = '''    for q in qs:
        opts, trunc, ok = fit_options([en(o) for o in (q.get("o") or [])], int(q.get("key") or 0))
        if not ok:
            raise EngineError("mongo set %s has an unusable question (uid=%s)" % (day, q.get("uid")))
        qt, qtr = fit_question(en(q.get("q")))
        expl = en(q.get("expl") or "")
        picked.append({"uid": q.get("uid"), "serial": q.get("uid"), "page": "", "topic": en(q.get("topic") or ""),
                       "q": qt, "o": opts, "key": int(q["key"]), "trunc": trunc + qtr,
                       "expl": expl[:600], "src_row": None})'''
assert old in s, "afo plan anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 5. quiz poll with explanation (+ fallback)
old = '''        poll = tg("sendPoll", chat_id=chat, question="%d/%d. %s" % (i + 1, N, q_body), options=q["o"],
                  type="regular", is_anonymous=False, allows_multiple_answers=False,
                  open_period=POLL_SECONDS, parse_mode="HTML")
        pid = ((poll or {}).get("poll") or {}).get("id")'''
new = '''        # v11.4.6 (admin order): the explanation travels WITH the question. Telegram shows an
        # in-poll explanation only on quiz polls, so the poll is a quiz poll (correct option marked)
        # and carries the first 200 chars; the reveal message after the 30 s window still lists the
        # full explanation + who was right/wrong.
        expl = fit_explanation(q.get("expl") or "")
        params = {"chat_id": chat, "question": "%d/%d. %s" % (i + 1, N, q_body), "options": q["o"],
                  "is_anonymous": False, "allows_multiple_answers": False,
                  "open_period": POLL_SECONDS, "parse_mode": "HTML"}
        if POLL_MODE == "quiz":
            params.update({"type": "quiz", "correct_option_id": int(q["key"])})
            if expl:
                params.update({"explanation": esc(expl), "explanation_parse_mode": "HTML"})
        else:
            params["type"] = "regular"
        poll = tg("sendPoll", **params)
        if not ((poll or {}).get("poll") or {}).get("id") and POLL_MODE == "quiz":
            log("quiz poll rejected for Q%d -> falling back to a regular poll" % (i + 1))
            params.pop("correct_option_id", None)
            params.pop("explanation", None)
            params.pop("explanation_parse_mode", None)
            params["type"] = "regular"
            poll = tg("sendPoll", **params)
        pid = ((poll or {}).get("poll") or {}).get("id")'''
assert old in s, "sendPoll anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 6. reveal uses the same english source
old = '''def reveal_text(job, plan, i, q, aq, names):
    """Native-quiz-bot style reveal right after the 30 s poll closes (v11.4)."""'''
new = '''def reveal_text(job, plan, i, q, aq, names):
    """Native-quiz-bot style reveal right after the 30 s poll closes (v11.4) — English (v11.4.6)."""'''
s = s.replace(old, new, 1)
io.open(E, "w", encoding="utf-8").write(s)
print("v11.4.6 applied (%d -> %d chars)" % (n0, len(io.open(E, encoding="utf-8").read())))
