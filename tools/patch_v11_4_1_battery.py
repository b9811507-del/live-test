#!/usr/bin/env python3
"""v11.4.1 battery additions: cases 21-25 (toppers >3 players, exact-time announce, reveal content,
tomorrow-plan scope, cross-day book continuation)."""
import io

P = "tests/fake_clock.py"
s = io.open(P, encoding="utf-8").read()
n0 = len(s)

NEW = '''

def _fixture_rows(sid):
    import csv as _csv
    rows = list(_csv.reader(open(os.path.join(tmp_fixtures(), sid + ".csv"), encoding="utf-8")))[1:]
    return [r for r in rows if len(r) > 9 and r[3].strip()]


def tmp_fixtures():
    return os.path.join(HERE, "fixtures", "sheets")


def case21_toppers_three(tmp):
    """21. more than 3 players: the message after the leaderboard names exactly the top 3 (medals),
    and each reveal lists who was right / wrong (native-quiz-bot style)."""
    day = "2026-09-17"
    players = [("9101", "Aarav", 0), ("9102", "Bhavna", 0), ("9103", "Chirag", 0),
               ("9104", "Divya", 1), ("9105", "Eshan", 2)]
    fp = os.path.join(tmp, "upd.json")
    json.dump([{"update_id": 500001 + i, "poll_answer": {
        "poll_id": "*", "user": {"id": int(u), "first_name": n, "username": None},
        "option_ids": [o]}} for i, (u, n, o) in enumerate(players)], open(fp, "w"))
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day),
                    env={"ENGINE_FAKE_UPDATES": fp})
    lb = [t for t in texts(log) if t.startswith("🏆 <b>LEADERBOARD")]
    top = [t for t in texts(log) if "TOP 3" in t]
    rv1 = [t for t in texts(log) if t.startswith("✅ <b>Q1/")]
    fx = _fixture_rows("malwa_vol1")
    key = "ABCDE".index(fx[0][9].strip().upper())
    exp = "✅ <b>Q1/20 · Correct answer: %s) %s</b>" % (chr(65 + key), fx[0][4 + key].strip())
    ranked = [l for l in (top[0].split("\\n") if top else []) if l.startswith(("🥇", "🥈", "🥉"))]
    wrong_names = [n for _, n, o in players if o != key]
    right_names = [n for _, n, o in players if o == key]
    ok = (len(lb) == 1 and all(n in lb[0] for _, n, _ in players)          # all 5 on the board
          and len(top) == 1 and len(ranked) == 3                            # exactly three toppers
          and all(m in top[0] for m in ("🥇", "🥈", "🥉"))
          and all(n in top[0] for n in right_names) and not any(n in top[0] for n in wrong_names)
          and len(rv1) == 1 and rv1[0].splitlines()[0] == exp               # reveal = sheet answer
          and "fixture explanation" in rv1[0]
          and len([t for t in texts(log) if t.startswith("✅ <b>Q")]) == 20)
    return ok, "players_on_board=%d toppers=%d medals=%s reveal0=%r" % (
        sum(1 for _, n, _ in players if n in (lb[0] if lb else "")), len(ranked),
        [l[:14] for l in ranked], (rv1[0].splitlines()[0] if rv1 else None))


def case22_exact_start(tmp):
    """22. nothing is posted before the exact slot time (ANNOUNCE_LEAD=0, v11.4); at 11:00:00 sharp
    the announce goes out, then the 15 s countdown, then Q1."""
    day = "2026-09-18"
    jr = empty_journal(day)
    p1, log1, st1 = mk(tmp, day + "T10:58:00+05:30", journal=jr)
    before_ok = (len(log1) == 0 and int(day_of(st1, day, "malwa").get("step", 0)) == 0)
    p2, log2, st2 = mk(tmp, day + "T11:00:00+05:30")
    ann = [t for t in texts(log2) if "MALWA BOOK VOL 1" in t and "poll auto-closes" in t]
    pl = polls(log2)
    cd = [e for e in methods(log2, "editMessageText", GROUP) if "Starting in" in (e.get("text") or "")]
    ok = (before_ok and len(ann) == 1 and len(pl) == 20 and cd
          and texts(log2).index(ann[0]) < methods(log2, "sendPoll", GROUP)[0]["question"])
    return ok, "messages_before_11:00=%d announce=%d polls=%d countdown_edits=%d first_poll=%r" % (
        len(log1), len(ann), len(pl), len(cd), (pl[0]["question"][:12] if pl else None))


def case23_reveal_sheet(tmp):
    """23. every reveal carries the sheet's correct option + the sheet's explanation column and the
    names of who answered right / wrong."""
    day = "2026-09-18"
    p, log, st = mk(tmp, day + "T14:30:00+05:30", journal=empty_journal(day))
    fx = _fixture_rows("iari")
    key = "ABCDE".index(fx[0][9].strip().upper())
    rvs = [t for t in texts(log) if t.startswith("✅ <b>Q")]
    first = [t for t in rvs if t.startswith("✅ <b>Q1/")]
    exp = "✅ <b>Q1/%d · Correct answer: %s) %s</b>" % (
        len([e for e in polls(log) if e["question"].startswith("1/")]) * 0 + 8, chr(65 + key), fx[0][4 + key].strip())
    ok = (len(rvs) == 8 and len(first) == 1 and first[0].splitlines()[0] == exp
          and "fixture explanation" in first[0]
          and ("👏" in first[0] or "❌" in first[0])                     # right/wrong player names
          and "Q8/8" in "\\n".join(rvs))
    return ok, "reveals=%d first=%r tail=%r" % (len(rvs), (first[0].splitlines()[0] if first else None),
                                                (rvs[-1].splitlines()[0] if rvs else None))


def case24_plan_scope(tmp):
    """24. tomorrow's plan: after 11:00 / 14:30 only the next day's page numbers (malwa + iari);
    after 18:00 the whole next-day test schedule (malwa + iari + AFO set)."""
    day = "2026-09-18"
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day))
    plans = [t for t in texts(log) if t.startswith("🗓")]
    noon_ok = (len(plans) == 1 and "11:00 AM" in plans[0] and "2:30 PM" in plans[0]
               and "6:00 PM" not in plans[0] and "AFO" not in plans[0])
    p2, log2, st2 = mk(tmp, day + "T18:00:00+05:30")
    plans2 = [t for t in texts(log2) if t.startswith("🗓")]
    eve = plans2[-1] if plans2 else ""
    eve_ok = (len(plans2) == 1 and "🌆 6:00 PM" in eve and "AFO MAINS TEST" in eve
              and "set" in eve)
    return noon_ok and eve_ok, "11:00 plan=%r | 18:00 plan=%r" % (
        (plans[0].replace("\\n", " | ")[:90] if plans else None), (eve.replace("\\n", " | ")[:120] or None))


def case25_cross_day(tmp):
    """25. the book advances across days: 16-Sep starts fresh, 17-Sep continues where 16-Sep ended
    (iari pages + malwa rows) and no question is repeated."""
    d1, d2 = "2026-09-16", "2026-09-17"
    p1, log1, st1 = mk(tmp, d1 + "T11:00:00+05:30", journal=empty_journal(d1))
    p2, log2, st2 = mk(tmp, d1 + "T14:30:00+05:30")
    i1 = day_of(st2, d1, "iari")
    m1 = day_of(st2, d1, "malwa")
    q1_malwa = {e["question"] for e in polls(log1)}
    q1_iari = {e["question"] for e in polls(log2)}
    p3, log3, st3 = mk(tmp, d2 + "T11:00:00+05:30")
    p4, log4, st4 = mk(tmp, d2 + "T14:30:00+05:30")
    i2, m2 = day_of(st4, d2, "iari"), day_of(st4, d2, "malwa")
    q2_malwa = {e["question"] for e in polls(log3)}
    q2_iari = {e["question"] for e in polls(log4)}
    ok = ((i1.get("plan") or {}).get("pages_list") == [2, 4, 5]                    # fresh Day 1
          and (m1.get("plan") or {}).get("row_from") == 0
          and (i2.get("plan") or {}).get("row_from") == (i1.get("plan") or {}).get("bidx_next")
          and (m2.get("plan") or {}).get("row_from") == (m1.get("plan") or {}).get("bidx_next") == 20
          and (i2.get("plan") or {}).get("pages_list") and (i2.get("plan") or {}).get("pages_list") != [2, 4, 5]
          and not (q1_iari & q2_iari) and not (q1_malwa & q2_malwa)                # no repeats
          and len(q2_iari) == 8 + 3 and len(q2_malwa) == 20)
    return ok, ("d1 iari pages=%s rows=%s..%s | d1 malwa rows=%s..%s | d2 iari pages=%s rows=%s..%s "
                "| d2 malwa rows=%s..%s | overlap(iari/malwa)=%d/%d") % (
        (i1.get("plan") or {}).get("pages_list"), (i1.get("plan") or {}).get("row_from"),
        (i1.get("plan") or {}).get("row_to"), (m1.get("plan") or {}).get("row_from"),
        (m1.get("plan") or {}).get("row_to"), (i2.get("plan") or {}).get("pages_list"),
        (i2.get("plan") or {}).get("row_from"), (i2.get("plan") or {}).get("row_to"),
        (m2.get("plan") or {}).get("row_from"), (m2.get("plan") or {}).get("row_to"),
        len(q1_iari & q2_iari), len(q1_malwa & q2_malwa))
'''

anchor = "\n\nCASES = ["
assert anchor in s
s = s.replace(anchor, NEW + "\n\nCASES = [", 1)
s = s.replace('''    ("20 one paid message per day (supersede + delete)", case20_paid_single),
]''',
'''    ("20 one paid message per day (supersede + delete)", case20_paid_single),
    ("21 toppers: exactly top 3 + reveal names", case21_toppers_three),
    ("22 exact slot time (nothing before 11:00)", case22_exact_start),
    ("23 reveal = sheet answer + explanation", case23_reveal_sheet),
    ("24 tomorrow-plan scope (pages vs full day)", case24_plan_scope),
    ("25 book advances across days (no repeats)", case25_cross_day),
]''')
io.open(P, "w", encoding="utf-8").write(s)
print("battery cases 21-25 added (%d -> %d chars)" % (n0, len(s)))
