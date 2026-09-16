#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy/run_cycle.sh — one engine cycle, safe for cron.
#   run_cycle.sh slotchain     # the whole daily dispatcher (wait/announce/polls/report)
#   run_cycle.sh keepwarm      # Render ping + student desk (DMs, payments, join links)
#   run_cycle.sh supply        # AFO bank audit (05:00 IST)
#   run_cycle.sh status        # print the journal
#   run_cycle.sh paid desk     # one manual desk pass
#  * flock  : two cycles can never overlap (protects getUpdates 409 and the journal)
#  * .env   : all secrets live in deploy/.env (never in cron, never in git)
#  * logs   : deploy/logs/<cmd>.log, rotated at 5 MB
# Free by design: this runs on your own VM — GitHub Actions minutes are NOT used.
# ─────────────────────────────────────────────────────────────────────────────
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
CMD="${1:-slotchain}"; shift || true
NAME="$(echo "$CMD$*" | tr ' /' '__')"
LOG="$HERE/logs/$NAME.log"
LOCK="/tmp/agri-$NAME.lock"

mkdir -p "$HERE/logs"
[ -f "$HERE/.env" ] || { echo "FATAL: $HERE/.env missing (copy .env.example -> .env)" >>"$LOG"; exit 2; }
set -a; . "$HERE/.env"; set +a
export TZ="${TZ:-Asia/Kolkata}"

# rotate
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ]; then
  mv "$LOG" "$LOG.1"
fi

{
  echo "─── $(date '+%F %T %Z') | $CMD $* | host $(hostname) ───"
} >>"$LOG"

# exec under lock; -n = exit immediately if another cycle of the same kind is running
cd "$REPO" || exit 3
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date '+%T') skipped: another '$NAME' cycle is still running" >>"$LOG"
  exit 0
fi

python3 engine/engine.py "$CMD" "$@" >>"$LOG" 2>&1
rc=$?
echo "$(date '+%T') done rc=$rc" >>"$LOG"
exit $rc
