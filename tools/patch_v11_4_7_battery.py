#!/usr/bin/env python3
"""v11.4.7 battery: no per-question reveal, no daily-schedule line, complete leaderboard in parts."""
import io

P = "tests/fake_clock.py"
s = io.open(P, encoding="utf-8").read()
n0 = len(s)

# ---------------- case 2: quiz polls only (no reveal messages), complete leaderboard, no CTA -----
s = s.replace('''          and len(reveals) == 20 and "📖" in reveals[0]                              # reveal + explanation each Q''',
'''          and len(reveals) == 0                                                      # v11.4.7: no reveal msg
          and len(lb) == 1                                                           # leaderboard complete''')
s = s.replace('''          and len(lb) == 1 and len(toppers) == 1 and len(docs) == 1 and len(tmr) == 1 and len(cta) == 1''',
'''          and len(toppers) == 1 and len(docs) == 1 and len(tmr) == 1 and len(cta) == 0   # no sign-off line''')
s = s.replace('''          and idx.index(ann[0]) < idx.index(lb[0]) < idx.index(toppers[0])           # ... < top3
          and idx.index(toppers[0]) < idx.index(cta[0]) and idx.index(tmr[0]) < idx.index(cta[0])''',
'''          and idx.index(ann[0]) < idx.index(lb[0]) < idx.index(toppers[0])           # ... < top3
          and idx.index(toppers[0]) < idx.index(tmr[0])                              # top3 < plan''')
s = s.replace('''          and all(e.get("explanation") for e in pl) and all(e.get("is_anonymous") is False for e in pl)''',
'''          and all(e.get("explanation") for e in pl) and all(e.get("is_anonymous") is False for e in pl)
          and all(e.get("correct_option_id") is not None for e in pl)''')

# ---------------- case 9: no reveals, leaderboard still whole -----------------------------------
s = s.replace('''    reveals = [t for t in texts(log) if t.startswith("✅ <b>Q")]''',
'''    reveals = [t for t in texts(log) if t.startswith("✅ <b>Q")]      # v11.4.7: must stay 0''')
s = s.replace('''          and len(reveals) == 28''', '''          and len(reveals) == 0''')
s = s.replace('''"iari.step=%s malwa.step=%s polls=%d reveals=%d iari_pages=%s pins=%s unpinned=%s plan=%d "''',
              '''"iari.step=%s malwa.step=%s polls=%d reveals=%d iari_pages=%s pins=%s unpinned=%s plan=%d "''')

# ---------------- case 21: reveal assertions -> in-poll assertions -------------------------------
old = '''    lb = [t for t in texts(log) if "LEADERBOARD" in t and t.startswith("🏆")]
    top = [t for t in texts(log) if "TOP 3" in t]
    rv1 = [t for t in texts(log) if t.startswith("✅ <b>Q1/")]'''
new = '''    lb = [t for t in texts(log) if "LEADERBOARD" in t and t.startswith("🏆")]
    top = [t for t in texts(log) if "TOP 3" in t]
    q1poll = [e for e in polls(log) if (e.get("question") or "").startswith("1/20.")]'''
assert old in s
s = s.replace(old, new, 1)
old = '''    ok = (len(lb) == 1 and all(n in board for _, n, _ in players)        # all 5 on the board
          and len(top) == 1 and len(ranked) == 3                         # exactly three toppers
          and all(m in top[0] for m in ("🥇", "🥈", "🥉"))
          and all(n in top[0] for n in right_names) and not any(n in top[0] for n in wrong_names)
          and len(rv1) == 1 and rv1[0].splitlines()[0] == exp            # reveal = sheet answer
          and "fixture explanation" in rv1[0]
          and len([t for t in texts(log) if t.startswith("✅ <b>Q")]) == 20)
    return ok, "players_on_board=%d toppers=%d medals=%s reveal0=%r" % (
        sum(1 for _, n, _ in players if n in board), len(ranked), [l[:14] for l in ranked],
        (rv1[0].splitlines()[0] if rv1 else None))'''
new = '''    ok = (len(lb) == 1 and all(n in board for _, n, _ in players)        # all 5 on the board
          and len(top) == 1 and len(ranked) == 3                         # exactly three toppers
          and all(m in top[0] for m in ("🥇", "🥈", "🥉"))
          and all(n in top[0] for n in right_names) and not any(n in top[0] for n in wrong_names)
          and len(q1poll) == 1 and q1poll[0].get("type") == "quiz"       # answer + explanation in the poll
          and q1poll[0].get("correct_option_id") == key
          and "fixture explanation" in (q1poll[0].get("explanation") or "")
          and len([t for t in texts(log) if t.startswith("✅ <b>Q")]) == 0)   # no reveal message
    return ok, "players_on_board=%d toppers=%d medals=%s poll.correct=%s poll.expl=%r" % (
        sum(1 for _, n, _ in players if n in board), len(ranked), [l[:14] for l in ranked],
        q1poll[0].get("correct_option_id") if q1poll else None,
        (q1poll[0].get("explanation") or "")[:60] if q1poll else None)'''
assert old in s
s = s.replace(old, new, 1)
s = s.replace('''    exp = "✅ <b>Q1/20 · Correct answer: %s) %s</b>" % (chr(65 + key), fx[0][4 + key].strip())''',
'''    exp = "✅ <b>Q1/20 · Correct answer: %s) %s</b>" % (chr(65 + key), fx[0][4 + key].strip())   # (unused here)''')

# ---------------- case 23: in-poll explanation instead of the reveal message --------------------
old = '''def case23_reveal_sheet(tmp):
    """23. every reveal carries the sheet's correct option + the sheet's explanation column and the
    names of who answered right / wrong."""
    day = "2026-09-19"
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T14:30:00+05:30",
                    journal=empty_journal(day, malwa={"step": 8}))
    fx = _fixture_rows("iari")
    key = "ABCDE".index(fx[0][9].strip().upper())
    rvs = [t for t in texts(log) if t.startswith("✅ <b>Q")]
    n = len(polls(log))
    first = [t for t in rvs if t.startswith("✅ <b>Q1/")]
    exp = "✅ <b>Q1/%d · Correct answer: %s) %s</b>" % (n, chr(65 + key), fx[0][4 + key].strip())
    ok = (n == 8 and len(rvs) == 8 and len(first) == 1 and first[0].splitlines()[0] == exp
          and "fixture explanation" in first[0]
          and ("👏" in first[0] or "❌" in first[0])                     # right/wrong player names
          and rvs[-1].startswith("✅ <b>Q8/8"))
    return ok, "iari_polls=%d reveals=%d first=%r tail=%r" % (
        n, len(rvs), (first[0].splitlines()[0] if first else None),
        (rvs[-1].splitlines()[0] if rvs else None))'''
new = '''def case23_reveal_sheet(tmp):
    """23. the sheet's correct option and explanation reach the student *inside the poll* (quiz poll),
    and no separate reveal message is posted (v11.4.7)."""
    day = "2026-09-19"
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T14:30:00+05:30",
                    journal=empty_journal(day, malwa={"step": 8}))
    fx = _fixture_rows("iari")
    key = "ABCDE".index(fx[0][9].strip().upper())
    pl = polls(log)
    q1 = [e for e in pl if (e.get("question") or "").startswith("1/8.")]
    ok = (len(pl) == 8 and len(q1) == 1 and q1[0].get("type") == "quiz"
          and q1[0].get("correct_option_id") == key
          and "fixture explanation" in (q1[0].get("explanation") or "")
          and all(e.get("type") == "quiz" and e.get("explanation") for e in pl)
          and not [t for t in texts(log) if t.startswith("✅ <b>Q")])
    return ok, "iari_polls=%d quiz=%d q1.correct=%s q1.expl=%r reveal_msgs=%d" % (
        len(pl), sum(1 for e in pl if e.get("type") == "quiz"), q1[0].get("correct_option_id") if q1 else None,
        (q1[0].get("explanation") or "")[:60] if q1 else None,
        len([t for t in texts(log) if t.startswith("✅ <b>Q")]))'''
assert old in s
s = s.replace(old, new, 1)

# ---------------- case 28: leaderboard completeness --------------------------------------------
NEW = '''

def case28_leaderboard_complete(tmp):
    """28. admin order: the leaderboard must be COMPLETE — with many players it goes out as several
    messages, every student is listed exactly once, every message stays under Telegram's 4096 limit
    and no message is cut in the middle of a row."""
    day = "2026-09-22"
    players = [("8%03d" % (100 + i), "Student%03d" % i, i % 4) for i in range(120)]
    fp = os.path.join(tmp, "upd_big.json")
    json.dump([{"update_id": 700000 + i, "poll_answer": {
        "poll_id": "*", "user": {"id": int(u), "first_name": n, "username": None},
        "option_ids": [o]}} for i, (u, n, o) in enumerate(players)], open(fp, "w"))
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day),
                    env={"ENGINE_FAKE_UPDATES": fp})
    lbs = [t for t in texts(log) if t.startswith("🏆") and "LEADERBOARD" in t]
    body = "\\n".join(lbs)
    missing = [n for _, n, _ in players if n not in body]
    dupes = [n for _, n, _ in players if body.count(n) > 1]
    whole = all(l.strip() == "" or "incorrect" in l or "LEADERBOARD" in l or "<b>" in l
                for t in lbs for l in t.split("\\n"))
    j = day_of(st, day, "malwa")
    ok = (len(lbs) >= 3 and not missing and not dupes and whole
          and all(len(t) <= 4096 for t in lbs)
          and "leaderboard continued" in lbs[1]
          and int(j.get("lb_parts") or 0) == len(lbs) and int(j.get("lb_rows") or 0) == len(players)
          and j.get("lb_sent") is True)
    return ok, "messages=%d rows=%s listed=%d/%d missing=%s dupes=%s journal.parts=%s lb_sent=%s" % (
        len(lbs), j.get("lb_rows"), len(players) - len(missing), len(players), missing[:3], dupes[:3],
        j.get("lb_parts"), j.get("lb_sent"))
'''
anchor = "\n\nCASES = ["
assert anchor in s
s = s.replace(anchor, NEW + anchor, 1)
s = s.replace('''    ("27 result file = day's test paper (book-file format)", case27_paper_file),
]''',
'''    ("27 result file = day's test paper (book-file format)", case27_paper_file),
    ("28 leaderboard complete (many players, no row lost)", case28_leaderboard_complete),
]''')
io.open(P, "w", encoding="utf-8").write(s)
print("v11.4.7 battery updated (%d -> %d chars)" % (n0, len(s)))
