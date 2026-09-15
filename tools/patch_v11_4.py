#!/usr/bin/env python3
"""One-shot patch v11.4 (admin order 2026-09-15, second batch).

1. paid-batches message is NOT sent any more (group stays clean); the enrolment desk is kept, inert
   until a student writes to the bot.
2. after every question (30 s over) a reveal message shows the correct option, the sheet EXPLANATION
   (in English) and who answered correctly / incorrectly — native-quiz-bot style.
3. HTML result file = the most recent test only, in test-paper style, now with the explanation.
4. announce goes out exactly at 11:00 / 14:30 / 18:00 IST, then the 15 s countdown, then Q1.
5. leaderboard = bold + spaced rows, then a TOP 3 message, then the HTML file, then tomorrow's plan.
6. iari = 3 book pages per day (was 5); malwa/iari cursors reset for a fresh Day 1 from 16-Sep.
Run from repo root: python3 tools/patch_v11_4.py
"""
import sys

# ================================================================= 1. translator strings
P = "engine/translator.py"
t = open(P, encoding="utf-8").read()


def trep(old, new, label):
    global t
    if old not in t:
        print("MISSING translator anchor:", label)
        sys.exit(1)
    t = t.replace(old, new, 1)


trep('''    "lb_empty": "No entries were recorded in this test. See you at the next one! 👀",''',
     '''    "lb_empty": "No entries were recorded in this test. See you at the next one! 👀",
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
    "schedule_pages_unknown": "(continues automatically)",''', "strings")

# ================================================================= 2. engine
P = "engine/engine.py"
s = open(P, encoding="utf-8").read()


def rep(old, new, label):
    global s
    if old not in s:
        print("MISSING engine anchor:", label, "|", old.splitlines()[0][:70])
        sys.exit(1)
    s = s.replace(old, new, 1)


rep('VERSION = "v11.1"', 'VERSION = "v11.4"', "version")
rep('''ANNOUNCE_LEAD = int(os.environ.get("ANNOUNCE_LEAD", "120"))   # announce 2 min before start''',
    '''ANNOUNCE_LEAD = int(os.environ.get("ANNOUNCE_LEAD", "0"))     # v11.4: announce exactly at 11:00/2:30/6:00''',
    "announce lead")
rep('''     "right": 1.0, "wrong": -0.25, "pages_per_day": 5, "sid": "iari", "label": "IARI BOOK MCQ 2026"},''',
    '''     "right": 1.0, "wrong": -0.25, "pages_per_day": 3, "sid": "iari", "label": "IARI BOOK MCQ 2026"},''',
    "iari 3 pages")

# --- sheet rows must carry the explanation column
rep('''        out.append({"serial": str(r[0]).strip(), "page": str(r[1]).strip(), "topic": str(r[2]).strip(),
                    "q": q, "opts": opts, "key": ki, "src_row": n})''',
    '''        out.append({"serial": str(r[0]).strip(), "page": str(r[1]).strip(), "topic": str(r[2]).strip(),
                    "q": q, "opts": opts, "key": ki, "src_row": n,
                    "expl": " ".join(str(r[10]).split()) if len(r) > 10 else ""})''', "sheet expl")

# --- picked questions carry the explanation (translated once, frozen into the plan)
rep('''        if ok:
            picked.append({"uid": "%s:%s" % (r["page"], r["serial"]), "serial": r["serial"], "page": r["page"],
                           "topic": r["topic"], "q": qt, "o": opts, "key": r["key"], "trunc": trunc + qtr,
                           "src_row": r["src_row"]})''',
    '''        if ok:
            expl = r.get("expl") or ""
            if expl and tr.needs_translation(expl):
                expl = tr.translate_safe(expl)          # explanation in English (cached)
            picked.append({"uid": "%s:%s" % (r["page"], r["serial"]), "serial": r["serial"], "page": r["page"],
                           "topic": r["topic"], "q": qt, "o": opts, "key": r["key"], "trunc": trunc + qtr,
                           "expl": expl[:600], "src_row": r["src_row"]})''', "picked expl")
rep('''        qt, qtr = fit_question(q.get("q"))
        picked.append({"uid": q.get("uid"), "serial": q.get("uid"), "page": "", "topic": "",
                       "q": qt, "o": opts, "key": int(q["key"]), "trunc": trunc + qtr, "src_row": None})''',
    '''        qt, qtr = fit_question(q.get("q"))
        expl = " ".join(str(q.get("expl") or "").split())
        if expl and tr.needs_translation(expl):
            expl = tr.translate_safe(expl)
        picked.append({"uid": q.get("uid"), "serial": q.get("uid"), "page": "", "topic": "",
                       "q": qt, "o": opts, "key": int(q["key"]), "trunc": trunc + qtr,
                       "expl": expl[:600], "src_row": None})''', "mongo expl")

# --- reveal + toppers + tomorrow plan helpers
rep('''def cta_text():
    return tr.t("cta")''',
    '''def cta_text():
    return tr.t("cta")


def _names(uid_list, names, cap=5):
    out = [names.get(u, "player%s" % u) for u in uid_list[:cap]]
    extra = len(uid_list) - len(out)
    return ", ".join(out) + (" +%d more" % extra if extra > 0 else "")


def reveal_text(job, plan, i, q, aq, names):
    """Native-quiz-bot style reveal right after the 30 s poll closes (v11.4)."""
    right = [u for u, v in aq.items() if v is not None and int(v) == int(q["key"])]
    wrong = [u for u, v in aq.items() if v is not None and int(v) != int(q["key"])]
    lines = [tr.t("reveal_correct", n=i + 1, total=plan["n"],
                  ans=esc("%s) %s" % (chr(65 + int(q["key"])), q["o"][int(q["key"])])))]
    if q.get("expl"):
        lines.append(tr.t("reveal_explain", text=esc(q["expl"])))
    if right:
        lines.append(tr.t("reveal_right", n=len(right), names=esc(_names(right, names))))
    if wrong:
        lines.append(tr.t("reveal_wrong", n=len(wrong), names=esc(_names(wrong, names))))
    if not right and not wrong:
        lines.append(tr.t("reveal_none"))
    return "\\n".join(lines)


def toppers_text(job, day, plan, rows):
    label = plan.get("label") or job.upper()
    if not rows:
        return tr.t("toppers_none", label=esc(label))
    lines = [tr.t("toppers_head", label=esc(label)), ""]
    for r in rows[:3]:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"], "•")
        lines.append(tr.t("toppers_row", medal=medal, name=esc(r["name"]), score="%+.1f" % r["score"],
                          right=r["right"], wrong=r["wrong"]))
    lines += ["", tr.t("toppers_thanks", n=plan["n"], players=len(rows))]
    return "\\n".join(lines)


def tomorrow_plan_text(job, day, st):
    """Tomorrow's plan (v11.4): malwa+iari pages after the 11:00 and 2:30 tests; the whole day after 6 PM."""
    tmr = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    jm = ((st.get("days") or {}).get(day) or {}).get("malwa") or {}
    ji = ((st.get("days") or {}).get(day) or {}).get("iari") or {}
    lines = [tr.t("schedule_head"), ""]
    want = ("malwa", "iari") if job in ("malwa", "iari") else ("malwa", "iari", "afo")
    try:
        if "malwa" in want:
            pm, _, _ = plan_malwa(day, {"vol": jm.get("vol", 0), "bidx": jm.get("bidx", 0)})
            if pm:
                pl = pages_sorted(pm.get("pages_list")) or []
                pages = ", ".join(str(p) for p in pl) if pl else str(pm.get("pages") or "").replace("Book pages ", "")
                lines.append(tr.t("schedule_malwa", label=esc(pm.get("label")), pages=esc(pages)))
            else:
                lines.append(tr.t("schedule_malwa", label="MALWA", pages=tr.t("schedule_pages_unknown")))
        if "iari" in want:
            pi, _, _ = plan_iari(day, {"bidx": ji.get("bidx", 0)})
            if pi:
                pl = pages_sorted(pi.get("pages_list")) or []
                pages = ", ".join(str(p) for p in pl) if pl else str(pi.get("pages") or "")
                lines.append(tr.t("schedule_iari", label=esc(pi.get("label")), pages=esc(pages)))
            else:
                lines.append(tr.t("schedule_iari", label="IARI BOOK MCQ 2026", pages=tr.t("schedule_pages_unknown")))
        if "afo" in want:
            set_no = "-"
            try:
                import afo_mongo
                db, _ = afo_mongo.db_handle()
                doc = db.afo_sets.find_one({"date": tmr}) or {}
                set_no = doc.get("set_no", "-")
            except Exception:
                pass
            lines.append(tr.t("schedule_afo", label=JOBS["afo"]["label"], set_no=set_no))
    except Exception as e:
        log("tomorrow plan skipped:", str(e)[:110])
        return None
    return "\\n".join(lines)''', "helpers")

# --- leaderboard: bold + spacing + toppers block
rep('''    out = [head, ""]
    for r in rows:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"]) or ("#%d." % r["rank"])
        out.append("%s <a href=\\"tg://user?id=%s\\">%s</a> — <b>%+.1f</b> · %d correct · %d incorrect"
                   % (medal, esc(r["uid"]), esc(r["name"]), r["score"], r["right"], r["wrong"]))
    return "\\n".join(out)''',
    '''    out = [head, ""]
    for r in rows:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"]) or ("#%d." % r["rank"])
        out.append("%s <a href=\\"tg://user?id=%s\\"><b>%s</b></a> — <b>%+.1f</b> · %d correct · %d incorrect"
                   % (medal, esc(r["uid"]), esc(r["name"]), r["score"], r["right"], r["wrong"]))
        if part == 0 and r["rank"] <= 3:
            out.append("")            # breathing room under the medal rows
    return "\\n".join(out)''', "leaderboard bold")

# --- polls: reveal after each question
rep('''        aq = ans.setdefault(str(i), {})
        off = drain(off, pid, POLL_SECONDS + 1.5, aq, names, hard)''',
    '''        aq = ans.setdefault(str(i), {})
        off = drain(off, pid, POLL_SECONDS + 1.5, aq, names, hard)
        # v11.4: native-quiz-bot style reveal (correct option + explanation + who was right)
        try:
            rv = tg("sendMessage", chat_id=chat, text=reveal_text(job, plan, i, q, aq, names),
                    parse_mode="HTML", disable_web_page_preview=True)
            if rv:
                j["reveals"] = int(j.get("reveals", 0)) + 1
        except Exception as e:
            log("reveal failed for Q%d: %s" % (i + 1, str(e)[:90]))''', "reveal send")

# --- after the leaderboard: toppers message (replaces congrats), file, then tomorrow plan
rep('''    # --- congrats (pinned)
    if not j.get("congrats_sent"):
        c = tg("sendMessage", chat_id=chat, text=congrats_text(job, day, plan, rows), parse_mode="HTML",
               disable_web_page_preview=True)
        if c:
            # v11.2: NOT pinned (only the announce is pinned in this group)
            j["congrats_sent"] = c["message_id"]
            jsave(st, "%s congrats (unpinned by rule)" % job)''',
    '''    # --- TOP 3 names (v11.4; replaces the old congrats message, never pinned)
    if not j.get("congrats_sent"):
        c = tg("sendMessage", chat_id=chat, text=toppers_text(job, day, plan, rows), parse_mode="HTML",
               disable_web_page_preview=True)
        if c:
            j["congrats_sent"] = c["message_id"]
            jsave(st, "%s top-3 (unpinned by rule)" % job)''', "toppers message")

rep('''        # v11.2: short note right after the leaderboard — what tomorrow's pages will be
        if not j.get("tmr_note") and job in ("malwa", "iari"):
            try:
                note = tomorrow_pages_note(job, day, st)
            except Exception as e:
                note = None
                log("tomorrow note failed:", str(e)[:100])
            if note:
                m2 = tg("sendMessage", chat_id=chat, text=note, parse_mode="HTML",
                        disable_web_page_preview=True)
                if m2:
                    j["tmr_note"] = m2["message_id"]
                    j["tmr_note_text"] = note
                    jsave(st, "%s tomorrow note" % job)
                    log("tomorrow note sent: %s" % note.replace("\\n", " ")[:120])''',
    '''''', "drop old note position")

rep('''    if not j.get("cta_sent"):
        c = tg("sendMessage", chat_id=chat, text=cta_text(), parse_mode="HTML", disable_web_page_preview=True)
        if c:
            j["cta_sent"] = c["message_id"]''',
    '''    # --- tomorrow's plan: AFTER the html file (11:00 / 2:30 -> tomorrow's pages; 6 PM -> the whole day)
    if not j.get("tmr_note"):
        try:
            note = tomorrow_plan_text(job, day, st)
        except Exception as e:
            note = None
            log("tomorrow plan failed:", str(e)[:100])
        if note:
            m2 = tg("sendMessage", chat_id=chat, text=note, parse_mode="HTML", disable_web_page_preview=True)
            if m2:
                j["tmr_note"] = m2["message_id"]
                j["tmr_note_text"] = note
                jsave(st, "%s tomorrow plan" % job)
                log("tomorrow plan sent: %s" % note.replace("\\n", " ")[:140])
    if not j.get("cta_sent"):
        c = tg("sendMessage", chat_id=chat, text=cta_text(), parse_mode="HTML", disable_web_page_preview=True)
        if c:
            j["cta_sent"] = c["message_id"]''', "tomorrow plan position")

# --- paid message OFF
rep('''    # --- v11.1: the LAST message of every test is the paid-batches showcase (payment links in buttons)
    if not j.get("paid_msg"):
        try:
            j["paid_msg"] = paid.post_after_test(SELF, chat, job=job, day=day)
        except Exception as e:
            log("paid message failed:", str(e)[:120])''',
    '''    # --- v11.4 (admin order): NO paid-batches message in the group any more.
    if (os.environ.get("PAID_SHOWCASE", "off") or "off").lower() in ("on", "1", "yes") and not j.get("paid_msg"):
        try:
            j["paid_msg"] = paid.post_after_test(SELF, chat, job=job, day=day)
        except Exception as e:
            log("paid message failed:", str(e)[:120])''', "paid off")

# --- cta stays the last message, but the schedule message comes before it: fix order comment
rep('''    j["step"] = 8
    j["done_at"] = istnow().isoformat(timespec="seconds")''',
    '''    j["step"] = 8
    j["msg_order"] = ["announce", "countdown", "polls+reveals", "leaderboard", "top3", "file", "tomorrow-plan", "cta"]
    j["done_at"] = istnow().isoformat(timespec="seconds")''', "order note")

open(P, "w", encoding="utf-8").write(s)
open("engine/translator.py", "w", encoding="utf-8").write(t)
print("v11.4 patch applied (engine + translator)")
