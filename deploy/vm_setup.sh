#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy/vm_setup.sh — one-shot setup of the FREE always-on VM (Ubuntu 22.04/24.04, x86 or ARM).
#   bash deploy/vm_setup.sh                 # first time
#   bash deploy/vm_setup.sh --code-only     # just refresh the code + deps
# It installs python + flock + git, creates the venv-free runtime, installs the cron file and
# prints the verification commands.  Nothing here touches GitHub Actions.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
USER_NAME="$(whoami)"
CODE_ONLY="${1:-}"

say() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }

if [ "$CODE_ONLY" != "--code-only" ]; then
  say "1/5 system packages (python3, pip, git, flock, ca-certificates, tzdata)"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-pip git util-linux ca-certificates tzdata
  say "2/5 timezone = Asia/Kolkata (slot times are IST)"
  sudo timedatectl set-timezone Asia/Kolkata || true
fi

say "3/5 python dependencies"
python3 -m pip install -q --user pymongo || python3 -m pip install -q --break-system-packages pymongo

say "4/5 runtime secrets file"
if [ ! -f "$HERE/.env" ]; then
  cp "$HERE/.env.example" "$HERE/.env"
  chmod 600 "$HERE/.env"
  echo "   created $HERE/.env  ->  fill it in:  nano $HERE/.env"
  echo "   (the system will not post anything until this file has real values)"
else
  chmod 600 "$HERE/.env"
  echo "   $HERE/.env already exists (left untouched)"
fi
mkdir -p "$HERE/logs"

if [ "$CODE_ONLY" != "--code-only" ]; then
  say "5/5 cron (free scheduler — no GitHub minutes)"
  tmp="$(mktemp)"
  sed "s#__USER__#$USER_NAME#g; s#__REPO__#$REPO#g" "$HERE/crontab.agri" >"$tmp"
  sudo cp "$tmp" /etc/cron.d/agri-quiz
  sudo chmod 644 /etc/cron.d/agri-quiz
  sudo chown root:root /etc/cron.d/agri-quiz
  rm -f "$tmp"
  sudo systemctl restart cron 2>/dev/null || sudo service cron restart 2>/dev/null || true
fi

cat <<TXT

──────────────────────────────────────────────────────────────────────────────
CHECKS (run these now)
  1) secrets          : nano $REPO/deploy/.env
  2) one manual cycle : $REPO/deploy/run_cycle.sh status        # journal
  3) desk dry run     : $REPO/deploy/run_cycle.sh keepwarm      # one desk pass
  4) cron installed   : cat /etc/cron.d/agri-quiz
  5) live log         : tail -f $REPO/deploy/logs/slotchain.log
  6) next test        : 11:00 IST MALWA · 14:30 IST IARI · 18:00 IST AFO   (auto)

GitHub Actions stays OFF for this repo — nothing is scheduled there any more.
──────────────────────────────────────────────────────────────────────────────
TXT
