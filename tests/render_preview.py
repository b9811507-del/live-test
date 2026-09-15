#!/usr/bin/env python3
"""tests/render_preview.py — renders the REAL group/DM texts with the REAL engine code (offline),
so the admin can see exactly what will be posted. Nothing is sent to Telegram.

Usage: python3 tests/render_preview.py [out.md] [out.html]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
os.environ.setdefault("ENGINE_FAKE", "1")
os.environ.setdefault("EXAM_TG_TOKEN", "fake")
os.environ.setdefault("CHAT_ID", "-1003784795446")
os.environ.setdefault("ADMIN_CHAT", "-100999")

import builder          # noqa: E402
import engine           # noqa: E402
import paid             # noqa: E402


def paper(job, day="2026-09-16"):
    """Deterministic paper for the preview: fixtures when ENGINE_FAKE_SHEETS is set, else the real sheets."""
    if job == "malwa":
        plan, _, _ = engine.plan_malwa(day, {"vol": 0, "bidx": 0})
    elif job == "iari":
        plan, _, _ = engine.plan_iari(day, {"bidx": 0})
    else:
        import afo_mongo
        db, flush = afo_mongo.db_handle()
        doc = db.afo_sets.find_one({"date": day}) or {}
        plan, _, _ = engine.plan_afo(day, {})
        plan["set_no"] = doc.get("set_no")
    return plan


ROWS = [
    {"rank": 1, "uid": "5391000001", "name": "Ravi Meena", "score": 18.75, "right": 19, "wrong": 1, "skip": 0},
    {"rank": 2, "uid": "5391000002", "name": "Sunita Devi", "score": 16.5, "right": 18, "wrong": 6, "skip": 0},
    {"rank": 3, "uid": "5391000003", "name": "Mohan Lal", "score": 14.25, "right": 15, "wrong": 3, "skip": 2},
    {"rank": 12, "uid": "5391000012", "name": "Pooja Sharma", "score": 6.0, "right": 7, "wrong": 4, "skip": 9},
]


def block(title, text, lang="text"):
    return "\n### %s\n```\n%s\n```\n" % (title, text)


def main():
    out_md = sys.argv[1] if len(sys.argv) > 1 else "/home/user/GROUP-MESSAGES-EN.md"
    out_html = sys.argv[2] if len(sys.argv) > 2 else "/home/user/SAMPLE-result-EN.html"
    day = "2026-09-16"
    m, i, a = paper("malwa", day), paper("iari", day), paper("afo", day)
    o = ["# GROUP + CHAT MESSAGES — professional English (v11.1)",
         "_Rendered by the real engine functions (offline Telegram). English only — no Hinglish._", ""]

    o.append("## A. MALWA BOOK VOL 1 — 11:00 AM (20 Q)")
    o += [block("1) Announce (pinned — the ONLY pinned message)", engine.announce_text("malwa", day, m)),
          block("2) 15-second countdown (same pinned message, edited)", engine.countdown_text("malwa", day, m, 15)),
          block("3) Countdown ticks", "Starting in 15s…  ·  Starting in 10s…  ·  Starting in 5s…  ·  "
                                      "Starting in 3s…  ·  Starting in 1s…  ·  Starting now — good luck!"),
          block("4) Poll #1 (topic tag + 30s auto-close)",
                "1/20. [General Agriculture] %s\n%s" % (
                    m["questions"][0]["q"], "\n".join("   %s) %s" % (chr(65 + k), x)
                                             for k, x in enumerate(m["questions"][0]["o"])))),
          block("5) Leaderboard (48 rows/message)", engine.leaderboard_text(day, "malwa", m, ROWS)),
          block("5b) RIGHT AFTER the leaderboard — tomorrow's pages note (short)",
                engine.tomorrow_pages_note("malwa", day, {"days": {day: {"malwa": {"vol": m.get("vol", 0),
                                                                              "bidx": m.get("bidx_next", 0)}}}})
                or "(no more pages -> series complete message instead)"),
          block("6) Result file (sent as document, NOT pinned)",
                engine.tr.t("rf_caption", label=m["label"], date=engine.day_label(day), n=m["n"])),
          block("7) Daily schedule line (one line)", engine.cta_text()),
          block("8) LAST MESSAGE OF THE TEST → paid batches (buttons = payment links)",
                paid.group_text() + "\n\n[buttons]\n" + "\n".join(
                    " · " + " | ".join(b["text"] for b in row) for row in
                    paid.group_keyboard(engine)["inline_keyboard"]))]

    o.append("## B. IARI BOOK MCQ 2026 — 2:30 PM (%d Q, pages %s)" % (i["n"], i["pages"]))
    o += [block("1) Announce (pinned — the ONLY pinned message)", engine.announce_text("iari", day, i)),
          block("2) Poll #1", "1/%d. [%s] %s\n%s" % (i["n"], i["questions"][0].get("topic", ""),
                                                     i["questions"][0]["q"],
                                                     "\n".join("   %s) %s" % (chr(65 + k), x)
                                                               for k, x in enumerate(i["questions"][0]["o"])))),
          block("3) Leaderboard header", engine.leaderboard_text(day, "iari", i, ROWS[:2]).split("\n")[0]),
          block("4) After the leaderboard — tomorrow's pages note",
                engine.tomorrow_pages_note("iari", day, {"days": {day: {"iari": {"bidx": i.get("bidx_next", 0)}}}})
                or "(series finished)")]

    o.append("## C. AFO MAINS TEST (NEW PATTERN) — 6:00 PM (%d Q, set_no %s)" % (a["n"], a.get("set_no")))
    o += [block("1) Announce (pinned)", engine.announce_text("afo", day, a)),
          block("2) Congratulation message (pinned)",
                engine.congrats_text("afo", day, a, [{"name": "Ravi Meena", "score": 92.0}]))]

    o.append("## D. STUDENT'S OWN CHAT BOX (private DM) — enrolment flow")
    o += [block("1) Tap a batch in the group → /start buy_afo", engine.tr.t(
                "dm_batch", emoji="🌆", title=paid.batch("afo")["title"],
                price=paid.batch("afo")["price"] or "Fee on enquiry", perks=paid.batch("afo")["perks"])),
          block("2) Student taps “I have paid”", engine.tr.t("dm_verify_wait", title=paid.batch("afo")["title"])),
          block("3) Payment confirmed → one-time join link in the same chat",
                engine.tr.t("dm_link", title=paid.batch("afo")["title"],
                            link="https://t.me/+AbCdEf123456", hours=paid.LINK_HOURS)),
          block("4) If the bot lacks the Invite Users right in that batch group",
                engine.tr.t("dm_link_pending", title=paid.batch("afo")["title"])),
          block("5) /mybatches", engine.tr.t("dm_mybatches", rows="• <b>AFO MAINS BATCH 2026</b> — joined 2026-09-16"))]

    o.append("## E. PIN POLICY (v11.2)")
    o += [block("what is pinned in @agriquizworld",
                "1) the announce of the current test  -> PINNED\n"
                "2) countdown (same message, edited)  -> not re-pinned\n"
                "3) leaderboard / tomorrow note       -> not pinned\n"
                "4) congratulations                   -> NOT pinned (was pinned in v11.1)\n"
                "5) result file (document)            -> not pinned\n"
                "6) daily schedule line               -> not pinned\n"
                "7) paid batches                      -> not pinned\n\n"
                "When the next test announces, the previous announce is unpinned automatically, so the group\n"
                "always has exactly ONE pinned message (the live/current announce). Stale pins from earlier\n"
                "runs that this engine posted (e.g. the cancelled 14-Sep announce 29092) are unpinned too.")]

    o.append("## F. ADMIN DMs (private, English)")
    o += [block("slot missed", engine.tr.t("adm_missed", job="IARI", time="2:30 PM")),
          block("bot lacks posting rights", engine.tr.t("adm_blocked", job="IARI", why="bot status=member")),
          block("new enrolment", engine.tr.t("adm_claim", title="AFO MAINS BATCH 2026", name="Ravi",
                                             uid="5391000001", mode="claim_auto", issued="yes"))]

    open(out_md, "w", encoding="utf-8").write("\n".join(o))

    # English result file sample (same builder the runner uses)
    ans = {"0": {"5391000001": 0, "5391000002": 2}, "1": {"5391000001": 1, "5391000003": 1}}
    builder.render_html(engine.result_data(day, "malwa", m, ROWS, ans), 0, m["label"], "AGRI QUIZ WORLD",
                        "@Arunkatyanquiz_bot", 48, True, out_html)
    print("wrote", out_md, "and", out_html)


if __name__ == "__main__":
    main()
