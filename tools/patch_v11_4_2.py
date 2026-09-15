#!/usr/bin/env python3
"""v11.4.2 — fake-mode injection fix + battery case rewrite (21-24).

The desk's startup peek calls getUpdates(offset=-1). In fake mode that consumed the injected update
batch, so the toppers case never saw its five players. A peek must not consume the batch.
"""
import io

EG = "engine/engine.py"
s = io.open(EG, encoding="utf-8").read()
old = '''    if os.environ.get("ENGINE_FAKE_UPDATES"):
        if _injected["served"]:
            return []
        _injected["served"] = True'''
new = '''    if os.environ.get("ENGINE_FAKE_UPDATES"):
        poff = params.get("offset")
        if poff in (None, -1):
            return []                      # offset=-1 is a peek (desk startup): never consumes the batch
        if _injected["served"]:
            return []
        _injected["served"] = True'''
assert old in s, "injected batch anchor not found"
s = s.replace(old, new, 1)
io.open(EG, "w", encoding="utf-8").write(s)

P = "tests/fake_clock.py"
t = io.open(P, encoding="utf-8").read()
start = t.index("def case21_toppers_three")
end = t.index("\n\nCASES = [")
NEW = '''def case21_toppers_three(tmp):
    """21. more than 3 players: the message after the leaderboard names exactly the top 3 (medals),
    and each reveal lists who was right / wrong (native-quiz-bot style)."""
    day = "2026-09-17"
    players = [("9101", "Aarav", 0), ("9102", "Bhavna", 0), ("9103", "Chirag", 0),
               ("9104", "Divya", 1), ("9105", "Eshan", 2)]
    fp = os.path.join(tmp, "upd.json")
    json.dump([{"update_id": 500001 + i, "poll_answer": {
        "poll_id": "*", "user": {"id": int(u), "first_name": n, "username": None},
        "option_ids": [o]}} for i, (u, n, o) in enumerate(players)], open(fp, "w"))
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day),
                    env={"ENGINE_FAKE_UPDATES": fp})
    lb = [t for t in texts(log) if "LEADERBOARD" in t and t.startswith("🏆")]
    top = [t for t in texts(log) if "TOP 3" in t]
    rv1 = [t for t in texts(log) if t.startswith("✅ <b>Q1/")]
    fx = _fixture_rows("malwa_vol1")
    key = "ABCDE".index(fx[0][9].strip().upper())
    exp = "✅ <b>Q1/20 · Correct answer: %s) %s</b>" % (chr(65 + key), fx[0][4 + key].strip())
    ranked = [l for l in (top[0].split("\\n") if top else []) if l.startswith(("🥇", "🥈", "🥉"))]
    wrong_names = [n for _, n, o in players if o != key]
    right_names = [n for _, n, o in players if o == key]
    board = lb[0] if lb else ""
    ok = (len(lb) == 1 and all(n in board for _, n, _ in players)        # all 5 on the board
          and len(top) == 1 and len(ranked) == 3                         # exactly three toppers
          and all(m in top[0] for m in ("🥇", "🥈", "🥉"))
          and all(n in top[0] for n in right_names) and not any(n in top[0] for n in wrong_names)
          and len(rv1) == 1 and rv1[0].splitlines()[0] == exp            # reveal = sheet answer
          and "fixture explanation" in rv1[0]
          and len([t for t in texts(log) if t.startswith("✅ <b>Q")]) == 20)
    return ok, "players_on_board=%d toppers=%d medals=%s reveal0=%r" % (
        sum(1 for _, n, _ in board and players if n in board), len(ranked), [l[:14] for l in ranked],
        (rv1[0].splitlines()[0] if rv1 else None))


def case22_exact_start(tmp):
    """22. the announce never goes out early: a run that starts 30 s before the slot still announces
    at 11:00:00 sharp, the 15 s countdown follows, and only then Q1."""
    day = "2026-09-18"
    clear_log(tmp)
    p1, log1, st1 = mk(tmp, day + "T10:59:30+05:30", journal=empty_journal(day))
    j = day_of(st1, day, "malwa")
    ann_at = j.get("announced_at") or ""
    sends = [e for e in log1 if e.get("chat") == GROUP and e["method"] == "sendMessage"]
    first_poll = polls(log1)[0] if polls(log1) else {}
    cd = [int(m.group(1)) for e in methods(log1, "editMessageText", GROUP)
          for m in [re.search(r"Starting in (\\d+)s", e.get("text") or "")] if m]
    def _dt(v):
        return dt.datetime.fromisoformat(v) if v else None
    gap = ((_dt(first_poll.get("t")) - _dt(ann_at)).total_seconds()
           if first_poll.get("t") and ann_at else -1)
    ok = (int(j.get("step", 0)) == 8 and ann_at >= day + "T11:00:00"
          and j.get("msg_ann") and sends and sends[0].get("message_id") == j["msg_ann"]
          and len(polls(log1)) == 20 and cd and max(cd) == 15 and gap >= 15)
    return ok, "announced_at=%s first_msg=announce=%s polls=%d countdown(max %s) announce->Q1=%ss" % (
        ann_at, bool(sends) and sends[0].get("message_id") == j.get("msg_ann"), len(polls(log1)),
        max(cd) if cd else None, int(gap))


def case23_reveal_sheet(tmp):
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
        (rvs[-1].splitlines()[0] if rvs else None))


def case24_plan_scope(tmp):
    """24. tomorrow's plan: after 11:00 / 14:30 only the next day's page numbers (malwa + iari);
    after 18:00 the whole next-day test schedule (malwa + iari + AFO set)."""
    day = "2026-09-15"
    _reset_afo_day(tmp, "2026-09-15")
    _reset_afo_day(tmp, "2026-09-16")
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day))
    plans = [t for t in texts(log) if t.startswith("🗓")]
    noon_ok = (len(plans) == 1 and "11:00 AM" in plans[0] and "2:30 PM" in plans[0]
               and "6:00 PM" not in plans[0] and "AFO" not in plans[0])
    clear_log(tmp)
    p2, log2, st2 = mk(tmp, day + "T18:00:00+05:30",
                       journal=empty_journal(day, malwa={"step": 8}, iari={"step": 8}))
    plans2 = [t for t in texts(log2) if t.startswith("🗓")]
    eve = plans2[-1] if plans2 else ""
    eve_ok = len(plans2) == 1 and "🌆 6:00 PM" in eve and "AFO MAINS TEST" in eve and "set" in eve
    return noon_ok and eve_ok, "11:00 plan=%s | 18:00 plan=%s" % (
        (plans[0].replace("\\n", " | ")[:80] if plans else None), (eve.replace("\\n", " | ")[:110] or None))


def polls_set(log):
    return {e["question"] for e in polls(log)}


def case25_cross_day(tmp):
    """25. the book advances across days: 16-Sep starts fresh, 17-Sep continues where 16-Sep ended
    (iari pages + malwa rows) and no question is repeated."""
    d1, d2 = "2026-09-16", "2026-09-17"
    clear_log(tmp)
    p1, log1, st1 = mk(tmp, d1 + "T11:00:00+05:30", journal=empty_journal(d1))
    clear_log(tmp)
    p2, log2, st2 = mk(tmp, d1 + "T14:30:00+05:30")
    i1, m1 = day_of(st2, d1, "iari"), day_of(st2, d1, "malwa")
    clear_log(tmp)
    p3, log3, st3 = mk(tmp, d2 + "T11:00:00+05:30")
    clear_log(tmp)
    p4, log4, st4 = mk(tmp, d2 + "T14:30:00+05:30")
    i2, m2 = day_of(st4, d2, "iari"), day_of(st4, d2, "malwa")
    p1i, p2i = (i1.get("plan") or {}), (i2.get("plan") or {})
    p1m, p2m = (m1.get("plan") or {}), (m2.get("plan") or {})
    ok = (p1i.get("pages_list") == [2, 4, 5] and p1m.get("row_from") == 0          # fresh Day 1
          and p2i.get("row_from") == p1i.get("bidx_next") and p2i.get("pages_list")
          and p2i.get("pages_list") != p1i.get("pages_list")
          and p2m.get("row_from") == p1m.get("bidx_next") == 20
          and len(polls(log1)) == 20 and len(polls(log2)) == 8 and len(polls(log3)) == 20
          and not (polls_set(log1) & polls_set(log3))                            # malwa no repeat
          and not (polls_set(log2) & polls_set(log4)))                           # iari no repeat
    return ok, ("d1 iari pages=%s rows=%s..%s | d1 malwa rows=%s..%s | d2 iari pages=%s rows=%s..%s "
                "| d2 malwa rows=%s..%s | seed=%s") % (
        p1i.get("pages_list"), p1i.get("row_from"), p1i.get("row_to"), p1m.get("row_from"),
        p1m.get("row_to"), p2i.get("pages_list"), p2i.get("row_from"), p2i.get("row_to"),
        p2m.get("row_from"), p2m.get("row_to"), (i2.get("plan_seed") or {}).get("seeded_from"))
'''
t = t[:start] + NEW + t[end:]

# case 20's inline reset helper -> shared module-level helper used by case 24 too
old = '''    def _reset_afo_day():
        """case 10 already consumed today's AFO set in this shared tree; put it back so the 18:00
        job can run here too (paid-message behaviour is what this case checks)."""
        bp = os.path.join(tmp, "tests", "fixtures", "afo_bank.json")
        b = json.load(open(bp, encoding="utf-8"))
        uids = set()
        for d in b["afo_sets"]:
            if d["date"] == day:
                d["status"] = "ready"
                uids = {str(q.get("uid")) for q in (d.get("questions") or [])}
        b["afo_used_q"] = [x for x in (b.get("afo_used_q") or []) if str(x.get("uid")) not in uids]
        json.dump(b, open(bp, "w", encoding="utf-8"), indent=1)

    # 20a: default (no flag) -> no paid message at all
    _reset_afo_day()'''
new = '''    # 20a: default (no flag) -> no paid message at all
    _reset_afo_day(tmp, day)'''
assert old in t, "case20 reset helper anchor not found"
t = t.replace(old, new, 1)
t = t.replace('''    # 20b: flag on -> supersede + delete behaviour
    _reset_afo_day()''',
'''    # 20b: flag on -> supersede + delete behaviour
    _reset_afo_day(tmp, day)''')
# shared helper
anchor = "def clear_log(tmp):"
helper = '''def _reset_afo_day(tmp, day):
    """an earlier case consumed this AFO set in the shared tree; put it back so later cases can run
    the 18:00 job too (their own assertions are what matter)."""
    bp = os.path.join(tmp, "tests", "fixtures", "afo_bank.json")
    b = json.load(open(bp, encoding="utf-8"))
    uids = set()
    for d in b["afo_sets"]:
        if d["date"] == day:
            d["status"] = "ready"
            uids = {str(q.get("uid")) for q in (d.get("questions") or [])}
    b["afo_used_q"] = [x for x in (b.get("afo_used_q") or []) if str(x.get("uid")) not in uids]
    json.dump(b, open(bp, "w", encoding="utf-8"), indent=1)


'''
assert anchor in t
t = t.replace(anchor, helper + anchor, 1)
# case 21 quick typo guard (board truthiness)
t = t.replace('sum(1 for _, n, _ in board and players if n in board)',
              'sum(1 for _, n, _ in players if n in board)')
io.open(P, "w", encoding="utf-8").write(t)
print("engine injection fix + cases 21-25 rewritten")
