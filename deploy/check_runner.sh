#!/usr/bin/env bash
# deploy/check_runner.sh <https://your-service.onrender.com>  [ADMIN_KEY]
# Verifies the free runner end-to-end: /ping, status JSON, whether cycles are actually running,
# and the next test slot. Run it from anywhere (curl only). Exit 0 = healthy.
set -u
BASE="${1:-}"
KEY="${2:-}"
if [ -z "$BASE" ]; then echo "usage: $0 https://your-service.onrender.com [ADMIN_KEY]"; exit 2; fi
BASE="${BASE%/}"
say() { printf '%-28s %s\n' "$1" "$2"; }

echo "checking $BASE …"
code=$(curl -s -o /tmp/_ping.txt -w '%{http_code}' --max-time 60 "$BASE/ping" || echo 000)
if [ "$code" != "200" ] || ! grep -q ok /tmp/_ping.txt; then
  say "GET /ping" "FAIL (http $code) — service so rahi hai (pinger lagao) ya deploy fail hua"
  echo "   → Render dashboard → Events/Logs dekho; free instance pehli request par 30-50 s leti hai"
  exit 1
fi
say "GET /ping" "ok (200)"

curl -s --max-time 60 "$BASE/" -o /tmp/_stat.json || true
python3 - <<'PY' /tmp/_stat.json
import json, sys, datetime as dt
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("%-28s %s" % ("GET /", "FAIL: status JSON nahi mila (%s)" % e)); raise SystemExit(1)
cyc = d.get("cycles") or {}
last = d.get("last") or {}
errs = d.get("last_error") or {}
print("%-28s %s" % ("runner started", d.get("started")))
print("%-28s %s" % ("host", d.get("host")))
print("%-28s %s" % ("now (IST)", d.get("now_ist")))
print("%-28s %s" % ("cycles so far", cyc))
for n in ("slotchain", "keepwarm", "status", "supply", "guard", "update"):
    if n in last:
        print("%-28s %s" % ("last %s" % n, last[n]))
if errs:
    print("%-28s %s" % ("ERRORS", errs))
for s in d.get("next_slots") or []:
    print("%-28s %s (in %s min)" % ("next slot", s.get("slot"), s.get("in_minutes")))
ok = bool(cyc.get("keepwarm") or cyc.get("slotchain")) and not errs
print("%-28s %s" % ("VERDICT", "HEALTHY — cron-engine chal raha hai" if ok else
                    "ATTENTION — cycles abhi shuru nahi hue (2 min baad dobara check karo)"))
raise SystemExit(0 if ok else 1)
PY
rc=$?
if [ -n "$KEY" ]; then
  echo "manual triggers (ADMIN_KEY ke saath):"
  echo "  $BASE/run/status?key=$KEY"
  echo "  $BASE/run/keepwarm?key=$KEY"
  echo "  $BASE/run/slotchain?key=$KEY   (live group me post karega — sirf slot time par)"
fi
echo
echo "cron-job.org me daalo:   $BASE/ping     (har 5 minute, method GET)"
exit $rc
