#!/usr/bin/env bash
# deploy/update.sh — pull the latest engine from GitHub main and refresh dependencies.
# Runs from cron at 09:45 IST (before the test window) and can be run by hand any time.
# The journal (state.json) is committed by the engine itself, so a plain pull is enough.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
LOG="$HERE/logs/update.log"
mkdir -p "$HERE/logs"
{
  echo "─── $(date '+%F %T %Z') update ───"
  cd "$REPO" || exit 3
  git config user.email "engine@vm.local" 2>/dev/null || true
  git config user.name  "agri-quiz-vm" 2>/dev/null || true
  git pull --rebase --autostash origin main && echo "code updated: $(git rev-parse --short HEAD)"
  python3 -m pip install -q --user pymongo 2>/dev/null || python3 -m pip install -q --break-system-packages pymongo
  python3 -m py_compile engine/engine.py engine/paid.py engine/razorpay.py engine/translator.py && echo "compile OK"
} >>"$LOG" 2>&1
tail -6 "$LOG"
