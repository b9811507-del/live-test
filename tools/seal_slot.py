#!/usr/bin/env python3
"""Seal a job for a day: it can never fire or resume (step=8 + missed). Optional push.

    python3 tools/seal_slot.py iari 2026-09-16 "owner order - stopped at 15:55 IST"
    python3 tools/seal_slot.py all  2026-09-16 "owner order" --push   # needs GITHUB_TOKEN
"""
import json, os, subprocess, sys

job = sys.argv[1] if len(sys.argv) > 1 else "all"
day = sys.argv[2] if len(sys.argv) > 2 else __import__("datetime").datetime.now(
    __import__("datetime").timezone(__import__("datetime").timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
why = sys.argv[3] if len(sys.argv) > 3 else "owner order"
push = "--push" in sys.argv

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state.json")
st = json.load(open(p, encoding="utf-8"))
jobs = ["malwa", "iari", "afo"] if job == "all" else [job]
now = __import__("datetime").datetime.now(
    __import__("datetime").timezone(__import__("datetime").timedelta(hours=5, minutes=30))
).isoformat(timespec="seconds")
d = st.setdefault("days", {}).setdefault(day, {})
for jb in jobs:
    j = d.setdefault(jb, {})
    if int(j.get("step", 0)) >= 8:
        print("  %-6s already sealed (step=%s)" % (jb, j.get("step"))); continue
    j["step"] = 8
    j["killed"] = {"at": now, "why": why, "by": "admin"}
    j["done_at"] = now
    print("  %-6s -> SEALED (step=8, killed=%s)" % (jb, now))
st["stop"] = {"jobs": ("all" if job == "all" else jobs), "day": None, "at": now, "why": why, "by": "admin"}
json.dump(st, open(p, "w", encoding="utf-8"), indent=0, sort_keys=True)
open(p, "a", encoding="utf-8").write("\n")
print("stop flag arming:", json.dumps(st["stop"]))
if push:
    tok = os.environ.get("GITHUB_TOKEN") or ""
    r = subprocess.run(["git", "-C", os.path.dirname(p), "commit", "-qam", "seal %s %s: %s" % (job, day, why)])
    print("commit rc", r.returncode)
