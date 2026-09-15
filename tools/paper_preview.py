#!/usr/bin/env python3
"""paper_preview.py — render the exact HTML the engine will post after a test, without touching
Telegram. Usage:  python3 tools/paper_preview.py 2026-09-16 iari  [out_dir]
Real Google Sheets are read (no fake fixtures), so the preview equals the live paper."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "engine"))

day = sys.argv[1] if len(sys.argv) > 1 else "2026-09-16"
job = sys.argv[2] if len(sys.argv) > 2 else "iari"
outdir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "out")
os.makedirs(outdir, exist_ok=True)

import builder  # noqa: E402
import engine  # noqa: E402

if job == "iari":
    plan, _, why = engine.plan_iari(day, {"bidx": 0})
else:
    plan, _, why = engine.plan_malwa(day, {"vol": 0, "bidx": 0})
if not plan:
    sys.exit("no plan for %s/%s (%s)" % (day, job, why))

DATA = engine.result_data(day, job, plan, [], {})
slug = engine.re.sub(r"[^A-Z0-9]+", "_", plan["label"].upper()).strip("_")
p = engine.paper_pages_text(job, plan)
pslug = engine.re.sub(r"[^A-Za-z0-9]+", "-", p).strip("-") or "all"
path = os.path.join(outdir, "%s_%s_p%s_%dQ.html" % (slug, day, pslug, plan["n"]))
builder.render_html(DATA, 0, plan["label"], "AGRI QUIZ WORLD", "@Arunkatyanquiz_bot", 48, True, path)
print("pages=%s  questions=%d  file=%s" % (p, plan["n"], path))
ex = sum(1 for k in DATA["key"] if k.get("expl"))
print("questions with explanation: %d/%d | score board rows: %d" % (ex, len(DATA["key"]), len(DATA["rows"])))
