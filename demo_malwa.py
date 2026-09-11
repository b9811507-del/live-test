#!/usr/bin/env python3
"""One-off DEMO of Malwa slot in @agriquizworld — v6 format, does NOT touch real pointers."""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))
import engine as E
E.STATE_PATH = "/tmp/demo_state.json"

st = {"ptr": {}, "days": {}, "afo": {"cursor": 0, "seed": 20260911, "closed": False}}
day = E.day_meta("malwa", st, "DEMO")
day["questions"] = day["questions"][:6]
day["title"] = "🔵 DEMO — " + day["title"]
E.log("demo day:", day["pages"], len(day["questions"]), "Q |", day["title"])

# 1. announcement (pinned) — clean 4 lines + small demo tag
ann = E.announce_text("malwa", "DEMO", day) + "\n<i>🔵 Demo — real test kal 11:00 AM se, exactly aisa hi</i>"
mid_ann = E.send(ann, pin=True)
E.log("announce", mid_ann)

# 2. countdown (compact for demo)
mid = E.send("⏳ <b>First poll in 5 seconds</b>")
for lbl in ("4️⃣", "3️⃣", "2️⃣", "1️⃣"):
    time.sleep(1.1)
    E.tg("editMessageText", chat_id=E.CHAT, message_id=mid, parse_mode="HTML", text=f"⏳ <b>{lbl}</b>")
time.sleep(1.1)
E.tg("editMessageText", chat_id=E.CHAT, message_id=mid, parse_mode="HTML", text="🚀 <b>TEST START</b>")
E.log("GO")

# 3. the polls (30s each, bilingual, quiz, auto-close) — live votes tracked
rows = E.run_test(st, "DEMO", "malwa", day)
E.log("voters:", len(rows), rows[:3])

# 4. leaderboard (demo: not pinned)
if rows:
    for m in E.leaderboard_msgs("malwa", "DEMO", day, rows):
        E.send(m)
        time.sleep(1.2)
    E.send(f"👥 <b>{len(rows)}</b> ne vote kiye · 📊 avg {sum(r['final'] for r in rows)/len(rows):.1f} · 🥇 {rows[0]['final']:.2f}")
else:
    E.send("💪 <b>Great effort to everyone who opened the polls!</b> Demo me koi vote nahi aaya — real test me roz leaderboard banega 🏆")

# 5. congrats
E.send(E.congrats_msg(rows))

# 6. file (NOT pinned — user order) + caption
path, name = E.gen_offline_file("malwa", "DEMO", day)
cap = (f"🎁 <b>Live test file</b> — {day['title']} · Pages {day['pages'][0]}-{day['pages'][1]} · "
       f"<b>bilingual EN+हिंदी</b> · <i>offline re-attempt — 👁 se answers</i>")
E.send_file(path, name, cap)
E.log("file", name, os.path.getsize(path))

# 7. CTA (paid batch message — below file, plain since demo)
E.send(E.cta_msg("malwa"))

# 8. close
E.send("✅ <b>Demo complete</b> — real tests: 🔜 kal se ☀️ 11:00 AM MALWA (Pages 1-4) · 🌤 2:30 PM IARI · "
       "🌆 6:00 PM AFO MAINS — roz, isi tarah 🚀")
E.log("DEMO DONE")
