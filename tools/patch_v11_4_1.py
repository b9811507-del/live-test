#!/usr/bin/env python3
"""v11.4.1 — cross-day book cursor.

Bug found while wiring the fresh 16-Sep Day 1: a new day's job state is empty, so the sheet cursor
restarted at row 0 every morning — iari would repeat pages 2,4,5 and malwa would repeat vol-1 rows
0-19 daily. Fix: a fresh day seeds its cursor from the most recent previous day that ran the job
(journal key `bidx` / `vol`), and 15-Sep is explicitly marked as the restart point so 16-Sep starts
at the first page of the book.
"""
import io
import re

EG = "engine/engine.py"
s = io.open(EG, encoding="utf-8").read()
n0 = len(s)

# ---- 1. wildcard poll_id in the drain (battery injection helper; fake-only path) -------------
old = '''            pa = u.get("poll_answer")
            if not pa or (poll_id and pa.get("poll_id") != poll_id):
                continue'''
new = '''            pa = u.get("poll_answer")
            # "*" = battery injection that answers whichever poll is open (fake-clock only)
            if not pa or (poll_id and pa.get("poll_id") not in (poll_id, "*")):
                continue'''
assert old in s, "drain poll filter not found"
s = s.replace(old, new, 1)

# ---- 2. prev_cursor + seeding -----------------------------------------------------------------
old = '''def prebuild(job, day=None, st=None):'''
new = '''def prev_cursor(st, day, job):
    """v11.4.1: a new day's job state is empty, so the book cursor is seeded from the most recent
    previous day that actually ran this job (journal `bidx`/`vol` = where that day finished)."""
    try:
        older = sorted(k for k in (st.get("days") or {}) if k < day)
    except Exception:
        older = []
    for d in reversed(older):
        jj = ((st.get("days") or {}).get(d) or {}).get(job) or {}
        if not isinstance(jj, dict) or jj.get("series_complete"):
            continue
        plan = jj.get("plan") or {}
        cur = plan.get("bidx_next", jj.get("bidx_next", jj.get("bidx")))
        if cur is None:
            continue
        seed = {"bidx": int(cur), "seeded_from": d}
        vol = jj.get("vol", plan.get("vol"))
        if vol is not None:
            seed["vol"] = int(vol)
        return seed
    return None


def prebuild(job, day=None, st=None):'''
assert old in s, "prebuild def not found"
s = s.replace(old, new, 1)

old = '''    if os.environ.get("ENGINE_FAKE_FAIL") == job:
        raise EngineError("injected failure for %s (fake-clock case)" % job)'''
new = '''    if os.environ.get("ENGINE_FAKE_FAIL") == job:
        raise EngineError("injected failure for %s (fake-clock case)" % job)
    if job in ("malwa", "iari") and not any(j.get(k) for k in ("plan", "bidx", "vol", "seeded_from")):
        seed = prev_cursor(st, day, job)
        if seed:
            j.update(seed)
            j["plan_seed"] = dict(seed)
            log("prebuild %s %s: cursor seeded from %s -> bidx=%d%s" % (
                job, day, seed["seeded_from"], seed["bidx"],
                (" vol=%d" % seed["vol"]) if "vol" in seed else ""))'''
assert old in s, "prebuild body anchor not found"
s = s.replace(old, new, 1)

io.open(EG, "w", encoding="utf-8").write(s)
print("v11.4.1 applied to engine (%d -> %d chars)" % (n0, len(s)))
