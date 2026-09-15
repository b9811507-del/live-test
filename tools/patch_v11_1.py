#!/usr/bin/env python3
"""One-shot patch: v11 -> v11.1
  * professional English message layer (translator.py)
  * announce -> 15 second countdown -> polls
  * paid-batches message as the LAST message after every test
  * desk pass (student DMs / payments / join links) in the keepwarm job
  * early runs defer (they only re-arm) instead of holding a runner
Run from the repo root: python3 tools/patch_v11_1.py
"""
import re
import sys

P = "engine/engine.py"
s = open(P, encoding="utf-8").read()
orig = s

REPL = [
    # ---------- imports / constants ----------
    ('VERSION = "v11"', 'VERSION = "v11.1"'),
    ('sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # sibling modules (builder, afo_mongo)',
     'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # siblings: builder, afo_mongo, translator, paid\n'
     'import paid                    # paid batches + enrolment + single-use join links (v11.1)\n'
     'import translator as tr        # professional English language layer (v11.1)'),
    ('WINDOW_BEFORE = 50 * 60          # start allowed from go-50min',
     'ALLOWED_UPDATES = ["message", "callback_query", "poll", "poll_answer", "chat_join_request", "my_chat_member"]\n'
     'ANNOUNCE_LEAD = int(os.environ.get("ANNOUNCE_LEAD", "120"))   # announce 2 min before start\n'
     'COUNTDOWN_SECS = int(os.environ.get("COUNTDOWN_SECS", "15"))  # v11.1: announce -> 15s countdown -> polls\n'
     'DEFER_SECS = int(os.environ.get("DEFER_SECS", "240"))         # run earlier than this only re-arms (saves runner minutes)\n'
     'WINDOW_BEFORE = 50 * 60          # start allowed from go-50min'),

    # ---------- English message builders ----------
    ('''def announce_text(job, day, plan):
    cfg = JOBS[job]
    return "\\n".join([
        "%s <b>%s</b>" % (cfg["emoji"], esc(plan.get("label") or cfg.get("label") or job.upper())),
        "📅 %s · ⏰ %s" % (day_label(day), cfg["time_label"]),
        "📝 %s questions · 30s each · ek answer, poll auto-close" % plan["n"],
        "🏆 +%s right · %s wrong · end me leaderboard + result file 📄"
        % (fmt_num(cfg["right"]), ("−" + fmt_num(abs(float(cfg["wrong"])))) if cfg["wrong"] < 0
           else fmt_num(cfg["wrong"])),
    ])


def countdown_text(job, day, plan, secs):
    cfg = JOBS[job]
    return "\\n".join([
        "%s <b>%s</b>" % (cfg["emoji"], esc(plan.get("label") or cfg.get("label") or job.upper())),
        "📅 %s · ⏰ %s" % (day_label(day), cfg["time_label"]),
        "📝 %s questions · 30s each" % plan["n"],
        "⏳ <b>START in %ds…</b>" % max(0, int(secs)),
    ])


def cta_text():
    return "🌾 Roz ka schedule: 11:00 AM Malwa Book · 2:30 PM IARI Book · 6:00 PM AFO Mains — @agriquizworld"''',
     '''def announce_text(job, day, plan):
    """4-line announce in professional English (locked shape: title / date+time / questions / scoring)."""
    cfg = JOBS[job]
    return "\\n".join([
        tr.t("ann_title", emoji=cfg["emoji"], label=plan.get("label") or cfg.get("label") or job.upper()),
        tr.t("ann_when", date=day_label(day), time=cfg["time_label"]),
        tr.t("ann_body", n=plan["n"]),
        tr.t("ann_score", right=fmt_num(cfg["right"]),
             wrong=fmt_num(abs(float(cfg["wrong"]))) if cfg["wrong"] < 0 else fmt_num(cfg["wrong"])),
    ])


def countdown_text(job, day, plan, secs):
    cfg = JOBS[job]
    return "\\n".join([
        tr.t("ann_title", emoji=cfg["emoji"], label=plan.get("label") or cfg.get("label") or job.upper()),
        tr.t("ann_when", date=day_label(day), time=cfg["time_label"]),
        tr.t("ann_body", n=plan["n"]).split(" · ")[0] + " · 30 seconds each",
        tr.t("cd_line", n=max(0, int(secs))),
    ])


def cta_text():
    return tr.t("cta")'''),

    ('''def congrats_text(job, day, plan, rows):
    label = plan.get("label") or job.upper()
    top = ("\\n🥇 Topper: <b>%s</b> — %+.1f" % (esc(rows[0]["name"]), rows[0]["score"])) if rows else ""
    tail = "" if rows else "\\nAbhi koi answer nahi aaya — kal phir milte hain! 👀"
    return ("🎉 <b>%s complete</b> — %s sawal, sabko dhanyavaad! 🌾%s%s"
            % (esc(label), plan["n"], top, tail))''',
     '''def congrats_text(job, day, plan, rows):
    label = plan.get("label") or job.upper()
    if rows:
        return tr.t("congrats", label=esc(label), n=plan["n"], name=esc(rows[0]["name"]),
                    score="%+.1f" % rows[0]["score"])
    return tr.t("congrats_nobody", label=esc(label))'''),

    ('''    head = ("🏆 <b>%s — LEADERBOARD</b> (%dQ · %s)" % (esc(label), plan["n"], fmt_pair(cfg["right"], cfg["wrong"]))
            if part == 0 else "🏆 <b>%s</b> — leaderboard contd…" % esc(label))
    if not rows:
        return head + "\\n\\nAbhi koi score nahi — kal phir milte hain! 👀"''',
     '''    head = (tr.t("lb_head", label=esc(label), n=plan["n"], right=fmt_num(cfg["right"]),
                 wrong=fmt_num(abs(float(cfg["wrong"]))))
            if part == 0 else tr.t("lb_head_contd", label=esc(label)))
    if not rows:
        return head + "\\n\\n" + tr.t("lb_empty")'''),

    ('''        out.append("%s <a href=\\"tg://user?id=%s\\">%s</a> — <b>%+.1f</b> (%d✓ %d✗)"
                   % (medal, esc(r["uid"]), esc(r["name"]), r["score"], r["right"], r["wrong"]))''',
     '''        out.append("%s <a href=\\"tg://user?id=%s\\">%s</a> — <b>%+.1f</b> · %d correct · %d incorrect"
                   % (medal, esc(r["uid"]), esc(r["name"]), r["score"], r["right"], r["wrong"]))'''),

    # ---------- English admin DMs ----------
    ('''            dm_admin("⚠️ %s announce pin nahi ho paya (bot ko pin rights do)." % job, "pin:" + job, 6 * 3600)''',
     '''            dm_admin(tr.t("adm_pin", job=job.upper()), "pin:" + job, 6 * 3600)'''),
    ('''            dm_admin("⚠️ %s slot %s IST miss ho gaya (go+4h cross) — seal kar diya, retro-fire nahi hoga."
                     % (job.upper(), JOBS[job]["time_label"]), "missed:" + job, 6 * 3600)''',
     '''            dm_admin(tr.t("adm_missed", job=job.upper(), time=JOBS[job]["time_label"]), "missed:" + job, 6 * 3600)'''),
    ('''        dm_admin("⛔ %s start nahi ho paya: %s\\nFix: @agriquizworld → Administrators → @Arunkatyanquiz_bot "
                 "ko Post+Pin rights do." % (job.upper(), why), "blocked:" + job, 1800)''',
     '''        dm_admin(tr.t("adm_blocked", job=job.upper(), why=why), "blocked:" + job, 1800)'''),
    ('''            dm_admin("❗️%s cycle error: %s" % (job.upper(), str(e)[:200]), "error:" + job, 3600)''',
     '''            dm_admin(tr.t("adm_error", job=job.upper(), msg=esc(str(e)[:200])), "error:" + job, 3600)'''),
    ('''        dm_admin("🛡 slot-guard: slot-chain %.0f min se stale tha -> revive kar diya (%s)."
                 % (stale_min, ",".join(todo)), "guard", 3600)''',
     '''        dm_admin(tr.t("adm_guard", mins="%.0f" % stale_min, jobs=", ".join(todo)), "guard", 3600)'''),

    ('''            m = tg("sendMessage", chat_id=CHAT, parse_mode="HTML", disable_web_page_preview=True, text=(
                "🎊 <b>%s COMPLETE</b> — poori series khatam! Sabhi players ko shukriya 🌾\\n"
                "Aaj se ye slot band. Naya series jald hi! 🔔" % esc(lab)))''',
     '''            m = tg("sendMessage", chat_id=CHAT, parse_mode="HTML", disable_web_page_preview=True,
                   text=tr.t("series_complete", label=esc(lab)))'''),
]

missing = []
for old, new in REPL:
    if old not in s:
        missing.append(old.splitlines()[0][:70])
    else:
        s = s.replace(old, new, 1)
if missing:
    print("MISSING ANCHORS:")
    for m in missing:
        print("  -", m)
    sys.exit(1)
open(P, "w", encoding="utf-8").write(s)
print("part 1 ok: english layer, constants (%d replacements)" % len(REPL))
