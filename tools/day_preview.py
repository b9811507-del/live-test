#!/usr/bin/env python3
"""day_preview.py — print the exact group messages the engine will post for one slot, using the
REAL sheets (no Telegram calls, nothing sent).  Usage: python3 tools/day_preview.py 2026-09-16 malwa
Player-dependent lines (reveal names, leaderboard, top 3) are shown with sample names."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "engine"))

day = sys.argv[1] if len(sys.argv) > 1 else "2026-09-16"
job = sys.argv[2] if len(sys.argv) > 2 else "malwa"

import engine  # noqa: E402
import translator as tr  # noqa: E402

# paper of the day (same call the live slot makes)
if job == "malwa":
    plan, _, why = engine.plan_malwa(day, {"vol": 0, "bidx": 0})
else:
    plan, _, why = engine.plan_iari(day, {"bidx": 0})
if not plan:
    sys.exit("no plan for %s/%s (%s)" % (day, job, why))

cfg = engine.JOBS[job]
N = plan["n"]
print("=" * 100)
print(">>> ANNOUNCE (11:00:00 sharp, then PINNED; older announce auto-unpinned)")
print("=" * 100)
print(engine.announce_text(job, day, plan))
print()
print(">>> COUNTDOWN (same pinned message is edited, nothing else posted)")
tick = " → ".join(tr.t("cd_line", n=n) for n in (15, 10, 5, 4, 3, 2, 1))
print(tick + " → " + tr.t("cd_go"))
print()
print(">>> POLLS (one open at a time, 30 s auto-close, 5 options, anonymous off)")
for i in (0, 1):
    q = plan["questions"][i]
    print("%d/%d. [%s] %s" % (i + 1, N, (q.get("topic") or "General")[:40], q["q"]))
    for j, o in enumerate(q["o"]):
        print("      %s) %s" % (chr(65 + j), o))
    print()
print("... isi tarah saare %d questions\n" % N)
print(">>> REVEAL after every question's 30 s window (v11.4) — sample with 3 students")
q = plan["questions"][0]
aq = {"9001": int(q["key"]), "9002": int(q["key"]), "9003": (int(q["key"]) + 1) % len(q["o"])}
names = {"9001": "Ravi Verma", "9002": "Anjali Meena", "9003": "Sunil Yadav"}
print(engine.reveal_text(job, plan, 0, q, aq, names))
print()
print(">>> LEADERBOARD (bold, extra spacing; 48 rows per message) — sample naming")
rows = [{"uid": "9001", "name": "Ravi Verma", "score": 17.75, "right": 18, "wrong": 1, "skip": 1, "rank": 1},
        {"uid": "9002", "name": "Anjali Meena", "score": 15.5, "right": 16, "wrong": 2, "skip": 2, "rank": 2},
        {"uid": "9003", "name": "Sunil Yadav", "score": 12.25, "right": 13, "wrong": 3, "skip": 4, "rank": 3},
        {"uid": "9004", "name": "Pooja Sharma", "score": 9.0, "right": 10, "wrong": 4, "skip": 6, "rank": 4}]
print(engine.leaderboard_text(day, job, plan, rows))
print()
print(">>> TOP 3 (after the leaderboard, never pinned)")
print(engine.toppers_text(job, day, plan, rows))
print()
print(">>> HTML FILE (in the group's interactive app format, unpinned)")
p, ptext = engine.paper_html(job, day, plan, out_dir="/tmp/preview")
print("filename : %s" % os.path.basename(p))
print("caption  : %s" % tr.t("rf_caption", label=plan["label"], date=engine.day_label(day), n=N, pages=ptext))
print()
print(">>> TOMORROW'S PLAN (v11.4: pages after 11:00 / 2:30, full schedule after 6:00 PM)")
st = {"days": {day: {"malwa": {"vol": 0, "bidx": plan.get("bidx_next", 0)},
                     "iari": {"bidx": plan.get("bidx_next", 0) if job == "iari" else 0}}}}
print(engine.tomorrow_plan_text(job, day, st))
print()
print(">>> SIGN-OFF (last message — NO paid-batch message any more, admin order v11.4)")
print(engine.cta_text())
