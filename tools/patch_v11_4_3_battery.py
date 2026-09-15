#!/usr/bin/env python3
"""v11.4.3 battery: case 26 — the explicit series-restart marker (admin order: fresh Day 1)."""
import io

P = "tests/fake_clock.py"
s = io.open(P, encoding="utf-8").read()

NEW = '''

def case26_series_restart(tmp):
    """26. admin order (fresh Day 1 from 16-Sep): with the restart marker set for that day the book
    goes back to the very first page even though the previous day consumed earlier rows."""
    d1, d2 = "2026-09-16", "2026-09-17"
    clear_log(tmp)
    p1, log1, st1 = mk(tmp, d1 + "T11:00:00+05:30", journal=empty_journal(d1))
    clear_log(tmp)
    p2, log2, st2 = mk(tmp, d1 + "T14:30:00+05:30")
    sp = os.path.join(tmp, "state.json")
    st = json.load(open(sp, encoding="utf-8"))
    st["series_reset"] = {"iari": d2, "malwa": d2}
    json.dump(st, open(sp, "w", encoding="utf-8"), indent=1, sort_keys=True)
    clear_log(tmp)
    p3, log3, st3 = mk(tmp, d2 + "T11:00:00+05:30")
    clear_log(tmp)
    p4, log4, st4 = mk(tmp, d2 + "T14:30:00+05:30")
    i2, m2 = day_of(st4, d2, "iari"), day_of(st4, d2, "malwa")
    i1 = day_of(st2, d1, "iari")
    ok = ((i2.get("plan") or {}).get("row_from") == 0 and (m2.get("plan") or {}).get("row_from") == 0
          and (m2.get("plan") or {}).get("vol") == 0
          and (i2.get("plan") or {}).get("pages_list") == (i1.get("plan") or {}).get("pages_list")
          and len(polls(log3)) == 20 and len(polls(log4)) == 8)
    return ok, "restart d2: iari rows=%s..%s pages=%s | malwa rows=%s..%s vol=%s" % (
        (i2.get("plan") or {}).get("row_from"), (i2.get("plan") or {}).get("row_to"),
        (i2.get("plan") or {}).get("pages_list"), (m2.get("plan") or {}).get("row_from"),
        (m2.get("plan") or {}).get("row_to"), (m2.get("plan") or {}).get("vol"))
'''
anchor = "\n\nCASES = ["
assert anchor in s
s = s.replace(anchor, NEW + "\n\nCASES = [", 1)
s = s.replace('''    ("25 book advances across days (no repeats)", case25_cross_day),
]''',
'''    ("25 book advances across days (no repeats)", case25_cross_day),
    ("26 fresh Day 1 restart marker (series_reset)", case26_series_restart),
]''')
io.open(P, "w", encoding="utf-8").write(s)
print("case 26 added")
