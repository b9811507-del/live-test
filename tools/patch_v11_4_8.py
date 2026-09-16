#!/usr/bin/env python3
"""v11.4.8 — BOOK-WISE tests use only 3 book pages (blocks) per attempt (admin order).

MALWA was a "20 questions/day" job, which spilled over ~3 page-blocks (and truncated the third one).
Now BOTH book tests are page-based, exactly the same rule as IARI:
  * iari  : 3 book pages  -> all their questions (real sheet: pages 2,4,5 = 35 Q on Day 1)
  * malwa : 3 sheet page-blocks ("1-2", "3-4", "5-6" — the sheet groups 7 questions per 2-page block)
            -> all their questions (Day 1 = 21 Q), and a block is never cut in half any more.
Cursor, series-restart marker and the "no repeats" guarantee are unchanged.
"""
import io

E = "engine/engine.py"
s = io.open(E, encoding="utf-8").read()
n0 = len(s)

# ---------------------------------------------------------------- config: malwa is page-based now
old = '''    "malwa": {"go": 11 * 3600, "time_label": "11:00 AM IST", "emoji": "☀️", "kind": "sheet-rotate",
              "right": 1.0, "wrong": -0.25, "n": 20, "batch": 150},'''
new = '''    "malwa": {"go": 11 * 3600, "time_label": "11:00 AM IST", "emoji": "☀️", "kind": "sheet-rotate",
              "right": 1.0, "wrong": -0.25, "n": 20, "batch": 150,
              "pages_per_day": 3},        # v11.4.8: 3 page-blocks per test (admin order)'''
assert old in s, "malwa cfg anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- plan_malwa: take 3 whole blocks
old = '''def plan_malwa(day, j):
    """20 Q/day from the current volume; batch bookkeeping = 150 rows; volume exhausted -> next volume next day."""
    vol = int(j.get("vol", 0))
    bidx = int(j.get("bidx", 0))
    skips, rolled = [], False
    while True:
        if vol >= len(VOLUMES):
            return None, skips, "series_complete"
        sid, name = VOLUMES[vol]
        rows = sheet_rows(sid)
        if bidx < len(rows):
            break
        vol, bidx, rolled = vol + 1, 0, True
    picked, nxt, skips = _take_questions(rows, bidx, JOBS["malwa"]["n"])'''
new = '''def plan_malwa(day, j):
    """v11.4.8 (admin order): exactly 3 book page-blocks per test — every question of those blocks
    (never a half block), the rest of the day's slot closes. Volume rollover + cursor as before."""
    vol = int(j.get("vol", 0))
    bidx = int(j.get("bidx", 0))
    skips, rolled = [], False
    while True:
        if vol >= len(VOLUMES):
            return None, skips, "series_complete"
        sid, name = VOLUMES[vol]
        rows = sheet_rows(sid)
        if bidx < len(rows):
            break
        vol, bidx, rolled = vol + 1, 0, True
    # the sheet's page column holds a block label ("1-2"); take the next 3 distinct labels
    labels, i = [], bidx
    while i < len(rows) and len(labels) < int(JOBS["malwa"].get("pages_per_day") or 3):
        lab = (rows[i].get("page") or "").strip() or str(_page_num(rows[i].get("page")))
        if lab not in labels:
            labels.append(lab)
        i += 1
    if not labels:
        labels = [(rows[bidx].get("page") or "").strip()]
    picked, nxt, skips = _take_questions(rows, bidx, len(rows) - bidx,
                                         used_pages={_page_num(x) for x in labels})'''
assert old in s, "plan_malwa anchor not found"
s = s.replace(old, new, 1)

old = '''    pr = [_page_num(p["page"]) for p in picked if _page_num(p["page"])]
    pmax = max([_page_max(p["page"]) for p in picked] or [0])
    plan = {"src": sid, "kind": "sheet", "n": len(picked), "label": name, "vol": vol, "vol_index": vol,
            "batch": bidx // JOBS["malwa"]["batch"] + 1, "row_from": bidx, "row_to": nxt,
            "bidx_next": nxt, "rolled": rolled,'''
new = '''    pr = [_page_num(p["page"]) for p in picked if _page_num(p["page"])]
    pmax = max([_page_max(p["page"]) for p in picked] or [0])
    plan = {"src": sid, "kind": "sheet", "n": len(picked), "label": name, "vol": vol, "vol_index": vol,
            "batch": bidx // JOBS["malwa"]["batch"] + 1, "row_from": bidx, "row_to": nxt,
            "bidx_next": nxt, "rolled": rolled, "pages_blocks": labels,'''
assert old in s, "plan dict anchor not found"
s = s.replace(old, new, 1)
io.open(E, "w", encoding="utf-8").write(s)
print("engine: malwa is now 3 page-blocks/test (%d -> %d chars)" % (n0, len(io.open(E, encoding='utf-8').read())))

# ---------------------------------------------------------------- fixtures: 7 questions per block (like the real sheet)
F = "tests/make_fixtures.py"
t = io.open(F, encoding="utf-8").read()
old = '''        page = "%d-%d" % (1 + i, 2 + i) if page_pairs else str(1 + i)'''
new = '''        # real MALWA sheet: ~7 questions per 2-page block -> "1-2", "1-2", …, "3-4", …
        b = i // 7
        page = ("%d-%d" % (2 * b + 1, 2 * b + 2)) if page_pairs else str(1 + i)'''
assert old in t, "malwa_rows anchor not found"
t = t.replace(old, new, 1)
io.open(F, "w", encoding="utf-8").write(t)
print("fixtures: malwa blocks now 7 questions per 2-page label")
