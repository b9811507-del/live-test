#!/usr/bin/env python3
"""v11.4.10 — safety guard for "late-fired" tests + owner STOP flag (16-Sep incident).

Incident: 14:30 IARI announced, the instance died right before "polls start", came back at
15:48 and the engine — which allows firing up to go+4h (WINDOW_AFTER) so a cold start never
loses a test — re-counted down and started posting the test 80 minutes late.

Fix 1 (always on): LATE_MAX_MIN (default 15). A slot that never began its polls and is more
than N minutes past its scheduled time is sealed MISSED instead of fired late. Tests that
already began (started_at set) still resume normally after a crash — no duplicate questions.

Fix 2 (kill switch): journal key "stop" = {"jobs": "all"|[job...], "day": "YYYY-MM-DD"|null,
"at": ..., "why": ...}. Honoured at the start of every cycle and re-checked from the journal
every 5 polls, so an owner can call off a running test without touching Render.
"""
import io, sys

p = "engine/engine.py"
s = io.open(p, encoding="utf-8").read()
if "LATE_MAX_MIN" in s:
    print("already patched"); sys.exit(0)

# 1) knob
s = s.replace(
    'WINDOW_AFTER = 4 * 3600          # after go+4h a missed slot stays missed\n',
    'WINDOW_AFTER = 4 * 3600          # after go+4h a missed slot stays missed\n'
    'LATE_MAX_MIN = int(os.environ.get("LATE_MAX_MIN", "15"))   # v11.4.10: never *start* a test this late\n',
    1)

# 2) helper: should we stop this job for this day?
helper = '''

def stop_requested(st, job, day):
    """v11.4.10 owner kill switch: journal key "stop". None -> no stop."""
    stop = (st or {}).get("stop") or None
    if not stop:
        return None
    if stop.get("day") and stop.get("day") != day:
        return None
    jobs = stop.get("jobs")
    if jobs in (None, "all") or job in jobs or (isinstance(jobs, str) and jobs == job):
        return stop
    return None


def read_stop_flag():
    """Read the journal's "stop" key from GitHub WITHOUT disturbing in-memory state."""
    keep = _S.get("st")
    try:
        st2 = jload(force=True) or {}
        return st2.get("stop")
    except Exception:
        return None
    finally:
        _S["st"] = keep
'''
s = s.replace("\ndef slot_phase(job, day, j):", helper + "\ndef slot_phase(job, day, j):", 1)

# 3) guard + stop at cycle level
old = '''    if ph == "idle":
        return "wait"'''
new = '''    if ph == "idle":
        return "wait"
    # v11.4.10 owner kill switch (journal key "stop")
    _stop = stop_requested(st, job, day)
    if _stop:
        j["step"] = 8
        j["killed"] = {"at": istnow().isoformat(timespec="seconds"), "why": _stop.get("why") or "owner stop",
                       "by": _stop.get("by") or "admin"}
        j["done_at"] = j["killed"]["at"]
        jsave(st, "%s killed by owner stop" % job)
        dm_admin(tr.t("adm_missed", job=job.upper(), time=JOBS[job]["time_label"]) + " (owner stop)",
                 "killed:" + job, 6 * 3600)
        return "killed"
    # v11.4.10 late guard: a test that never began must not start this long after its slot time
    if ph == "late" and not j.get("started_at"):
        late_min = int((istnow() - go_dt(day, job)).total_seconds() // 60)
        if late_min > LATE_MAX_MIN:
            j["step"] = 8
            j["missed"] = True
            j["late_sealed"] = {"go": go_dt(day, job).isoformat(timespec="seconds"),
                                "sealed_at": istnow().isoformat(timespec="seconds"), "late_min": late_min}
            j["done_at"] = j["late_sealed"]["sealed_at"]
            jsave(st, "%s late-sealed (%d min past slot, polls never began)" % (job, late_min))
            log("late guard: %s sealed (no polls started, %d min late)" % (job, late_min))
            if job == "afo":
                try:
                    import afo_mongo
                    db, flush = afo_mongo.db_handle()
                    doc = db.afo_sets.find_one({"date": day}) or {}
                    if doc.get("status") == "running":
                        db.afo_sets.update_one({"date": day}, {"$set": {
                            "status": "ready", "note": "late-sealed — set unused"}})
                        flush()
                except Exception as e:
                    log("mongo release failed:", str(e)[:80])
            dm_admin(tr.t("adm_missed", job=job.upper(), time=JOBS[job]["time_label"])
                     + " (late guard: %d min, polls never began)" % late_min, "late-seal:" + job, 6 * 3600)
            return "missed"'''
assert old in s
s = s.replace(old, new, 1)

# 4) poll loop: honour the stop flag (re-checked from the journal every 5 questions)
old2 = '''    for i in range(resume_at, N):
        if time.time() > hard:'''
new2 = '''    for i in range(resume_at, N):
        if i % 5 == 0:                            # v11.4.10: pick up an owner STOP mid-test
            _rf = read_stop_flag()
            if _rf:
                st["stop"] = _rf
            if stop_requested(st, job, day):
                j["killed"] = {"at": istnow().isoformat(timespec="seconds"), "why": "owner stop mid-test",
                               "q": i + 1}
                j["step"] = 8
                j["done_at"] = j["killed"]["at"]
                jsave(st, "%s killed mid-test at Q%d (owner stop)" % (job, i + 1))
                log("STOP flag honoured: %s killed at Q%d" % (job, i + 1))
                dm_admin(tr.t("adm_missed", job=job.upper(), time=JOBS[job]["time_label"])
                         + " (owner stop at Q%d)" % (i + 1), "killed-mid:" + job, 6 * 3600)
                return "killed"
        if time.time() > hard:'''
assert old2 in s
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("patched engine.py (LATE_MAX_MIN=%s guard + owner STOP flag)" % "15")
