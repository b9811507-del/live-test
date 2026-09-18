#!/usr/bin/env python3
"""web.py — FREE always-on runner for the exam engine (NO GitHub Actions minutes, NO card).

One tiny HTTP app does two jobs:

  1) keep-awake: self-ping thread (4 min) + GET /ping for any external uptime pinger
  2) the scheduler, in-process      every cycle = subprocess `python3 engine/engine.py <cmd>`
        slotchain  every 60 s  during 10:00–19:30 IST   → 11:00 / 14:30 / 18:00 tests
        keepwarm   every 3 min, 24×7                     → student desk: DMs, payments, join links
        inbox      every 40 s, 24×7                     → fast student replies/buttons (skips during live tests)
        supply     05:00 IST daily                       → AFO bank audit (never posts)
        guard      22:00 IST daily                       → safety net (seal open slots)
        update     09:45 IST daily                       → git pull the latest engine

Each cycle runs under a file lock, so two cycles can never overlap (protects the bot's getUpdates
stream) and a slow test can never be started twice.

Endpoints
    GET /                 status JSON (version, cycles, last runs, next slots)
    GET /ping             "ok" (3 bytes) — point any uptime/cron pinger here
    GET /wake             204, empty body (0 bytes) — for monitors with a tiny response limit
    GET /t                one-line status (~150 bytes) for size-capped monitors
    GET /run/<cmd>?key=…  manual trigger (protected by ADMIN_KEY); cmd in slotchain|keepwarm|guard|supply|status

Run locally:   PORT=8080 python3 engine/web.py
Free hosts:    Render free Web Service (start command: python3 engine/web.py) — no card needed
               Hugging Face Docker Space (port 7860) · Replit (port 8080) · any old phone/PC
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import ThreadingMixIn

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # repo root
PY = sys.executable or "python3"
PORT = int(os.environ.get("PORT", "8080"))
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
LOCKDIR = os.environ.get("RUNNER_LOCKDIR", "/tmp")
LOGDIR = os.path.join(HERE, "logs")
ADMIN_KEY = (os.environ.get("ADMIN_KEY") or "").strip()
# v11.4.13: Telegram webhook endpoint for the paid bot -> /ph/<ADMIN_KEY>; updates are appended
# to this spool file and drained by `engine.py ph` within ~1 s (instant student replies).
PAID_SPOOL = os.environ.get("PAID_SPOOL") or "/tmp/agri_paid_spool.jsonl"
# self keep-awake: free hosts spin the service down after ~15 min WITHOUT inbound HTTP traffic.
# Asking our own public URL from the inside counts as inbound traffic, so the instance never sleeps —
# no external pinger and no GitHub minutes needed. Set SELF_PING_URL="" to switch it off.
SELF_PING_URL = (os.environ.get("SELF_PING_URL") or "https://live-test-8wu1.onrender.com/ping").strip()
SELF_PING_SECS = int(os.environ.get("SELF_PING_SECS") or "240")      # 4 min < 15 min idle limit

try:
    import fcntl                                    # Linux/macOS (all free hosts above)
except Exception:                                   # pragma: no cover
    fcntl = None

STATE = {
    "started": dt.datetime.now(IST).isoformat(timespec="seconds"),
    "cycles": {},                                   # name -> count
    "last": {},                                     # name -> {at, rc, secs}
    "last_error": {},
    "running": {},                                  # name -> started-at (while a cycle is live)
    "host": os.environ.get("RENDER_SERVICE_NAME") or os.environ.get("HOSTNAME") or "runner",
}
_LOCK = threading.Lock()


# --------------------------------------------------------------------------- one engine cycle
def run_cycle(name, args, timeout=5400):   # 90 min: warm-wait + a 50-Q AFO test + report
    """Run `engine.py <args…>` in a subprocess under a lock. Returns (rc, seconds) or (-1, 0) if busy."""
    os.makedirs(LOGDIR, exist_ok=True)
    lock_path = os.path.join(LOCKDIR, "agri-runner-%s.lock" % name)
    handle = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    if fcntl:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(handle)
            return (-1, 0)                          # an identical cycle is already running
    with _LOCK:
        STATE["running"][name] = dt.datetime.now(IST).isoformat(timespec="seconds")
    t0 = time.time()
    rc = 1
    try:
        with open(os.path.join(LOGDIR, "%s.log" % name), "a", encoding="utf-8") as lf:
            lf.write("\n─── %s | %s %s ───\n" % (dt.datetime.now(IST).isoformat(timespec="seconds"),
                                               " ".join(args), STATE["host"]))
            lf.flush()
            env = os.environ.copy()
            env.setdefault("TZ", "Asia/Kolkata")
            if env.get("ENGINE_FAKE") == "1":        # smoke-test mode must never write the real journal
                env.setdefault("ENGINE_STATE", os.path.join(tempfile.gettempdir(), "agri_fake_state.json"))
            p = subprocess.run([PY, os.path.join("engine", "engine.py")] + list(args), cwd=HERE,
                               stdout=lf, stderr=subprocess.STDOUT, timeout=timeout, env=env)
            rc = p.returncode
    except subprocess.TimeoutExpired:
        rc = 124
    except Exception as e:                          # never let the scheduler die
        rc = 125
        with _LOCK:
            STATE["last_error"][name] = str(e)[:200]
    secs = round(time.time() - t0, 1)
    try:                                       # surface the engine's own output in the host log
        tail = open(os.path.join(LOGDIR, "%s.log" % name), encoding="utf-8", errors="replace").read().splitlines()[-12:]
        for line in tail:
            print("[%s] %s" % (name, line[:220]), flush=True)
    except Exception:
        pass
    print("[%s] cycle finished rc=%s in %ss" % (name, rc, secs), flush=True)
    with _LOCK:
        STATE["running"].pop(name, None)
        STATE["cycles"][name] = STATE["cycles"].get(name, 0) + 1
        STATE["last"][name] = {"at": dt.datetime.now(IST).isoformat(timespec="seconds"),
                               "rc": rc, "secs": secs}
    try:
        os.close(handle)
    except Exception:
        pass
    return (rc, secs)


# --------------------------------------------------------------------------- schedule
def istnow():
    return dt.datetime.now(IST)


def in_window(t, start_min, end_min):
    m = t.hour * 60 + t.minute
    return start_min <= m <= end_min


def daily_due(name, hhmm, now, window_min=45):
    """True inside a short window right after hh:mm IST and only if the job has not run since.
    The window stops a host cold-start at 20:00 from firing the 05:00 audit (or the 22:00 guard)."""
    hh, mm = hhmm
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if not (target <= now <= target + dt.timedelta(minutes=window_min)):
        return False
    last = STATE["last"].get(name) or {}
    try:
        last_dt = dt.datetime.fromisoformat(last.get("at")) if last.get("at") else None
    except Exception:
        last_dt = None
    return now >= target and (last_dt is None or last_dt < target)


def scheduler():
    """One thread, one decision per loop — the same cadence the cron file used on a VM."""
    slots = {}
    while True:
        try:
            now = istnow()
            # 1) tests: every 60 s inside the daily window
            if in_window(now, 10 * 60, 19 * 60 + 30):
                if time.time() - slots.get("slotchain", 0) >= 60:
                    slots["slotchain"] = time.time()
                    threading.Thread(target=run_cycle, args=("slotchain", ["slotchain"]),
                                     daemon=True).start()
            # 2) student desk: every 3 min, always
            if time.time() - slots.get("keepwarm", 0) >= 180:
                slots["keepwarm"] = time.time()
                threading.Thread(target=run_cycle, args=("keepwarm", ["keepwarm"]), daemon=True).start()
            # 2b) fast inbox: student taps answered within ~40 s (admin speed order 18-Sep)
            if time.time() - slots.get("inbox", 0) >= 40:
                slots["inbox"] = time.time()
                threading.Thread(target=run_cycle, args=("inbox", ["inbox"]), daemon=True).start()
            # 3) daily jobs
            if daily_due("supply", (5, 0), now) and "supply" not in STATE["running"]:
                threading.Thread(target=run_cycle, args=("supply", ["supply"]), daemon=True).start()
            if daily_due("guard", (22, 0), now) and "guard" not in STATE["running"]:
                threading.Thread(target=run_cycle, args=("guard", ["guard"]), daemon=True).start()
            if daily_due("update", (9, 45), now) and "update" not in STATE["running"]:
                threading.Thread(target=_update, daemon=True).start()
        except Exception as e:
            with _LOCK:
                STATE["last_error"]["scheduler"] = str(e)[:200]
        time.sleep(20)


def _update():
    """Code refresh. On Render/Northflank-style hosts the platform redeploys automatically on every
    push, so this is OFF by default (set RUNNER_GIT_UPDATE=on for the VM/cron route)."""
    with _LOCK:
        STATE["running"]["update"] = istnow().isoformat(timespec="seconds")
    if (os.environ.get("RUNNER_GIT_UPDATE", "off") or "off").lower() not in ("on", "1", "yes"):
        with _LOCK:
            STATE["running"].pop("update", None)
            STATE["last"]["update"] = {"at": istnow().isoformat(timespec="seconds"), "rc": 0, "secs": 0,
                                       "note": "skipped (host auto-deploys on push; RUNNER_GIT_UPDATE=on to force)"}
        return
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, "update.log"), "a", encoding="utf-8") as lf:
            p = subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=HERE,
                               stdout=lf, stderr=subprocess.STDOUT, timeout=300)
        rc = p.returncode
    except Exception as e:
        rc, _ = 125, str(e)
    with _LOCK:
        STATE["running"].pop("update", None)
        STATE["last"]["update"] = {"at": istnow().isoformat(timespec="seconds"), "rc": rc, "secs": 0}


# --------------------------------------------------------------------------- http
def _paid_wake():
    """Drain the webhook spool immediately after a tap lands (no waiting for the 40 s tick)."""
    def _loop():
        for _ in range(8):
            try:
                run_cycle("ph", ["ph"], timeout=120)
            except Exception:
                return
            try:
                if not os.path.exists(PAID_SPOOL) or os.path.getsize(PAID_SPOOL) == 0:
                    return
            except Exception:
                return
            time.sleep(0.7)
    threading.Thread(target=_loop, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "agri-quiz-runner"

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):               # keep the host's log clean
        return

    def do_POST(self):
        # v11.4.13: Telegram bot webhook — POST /ph/<ADMIN_KEY>. Validates secret header,
        # appends the raw update to the spool, kicks the drainer, ACKs fast.
        path = self.path.split("?")[0].rstrip("/")
        if not path.startswith("/ph/"):
            return self._send(404, "no endpoint\n")
        key = path[len("/ph/"):]
        if not ADMIN_KEY or key != ADMIN_KEY:
            return self._send(403, "denied\n")
        expected = (os.environ.get("PAID_WEBHOOK_SECRET") or "").strip()
        got = (self.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if expected and got != expected:
            return self._send(401, "bad secret\n")
        try:
            ln = int(self.headers.get("Content-Length") or 0)
            if ln <= 0 or ln > 65536:
                raise ValueError("size")
            upd = json.loads(self.rfile.read(ln).decode("utf-8"))
            if not isinstance(upd, dict) or "update_id" not in upd:
                raise ValueError("shape")
            line = json.dumps(upd, separators=(",", ":"))
            if "\n" in line:
                raise ValueError("nl")
            with open(PAID_SPOOL, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except Exception:
            return self._send(400, "bad update\n")
        _paid_wake()
        return self._send(200, "ok\n")

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/ping":                          # keep-awake
            ua = self.headers.get("User-Agent", "") or ""
            ip = self.headers.get("X-Forwarded-For") or self.client_address[0]
            with _LOCK:
                rec = STATE.setdefault("ping_in", {"external": 0, "self": 0})
                key = "self" if ua.startswith("agri-selfping") else "external"
                rec[key] = (rec.get(key) or 0) + 1
                rec["last_" + key] = {"at": istnow().isoformat(timespec="seconds"), "ua": ua[:70], "ip": ip[:60]}
            if key == "external":
                print("inbound ping from %s (%s)" % (ua[:60], ip[:40]), flush=True)
            return self._send(200, "ok\n")
        if path == "/wake":                          # 0-byte keep-awake: 204 No Content
            with _LOCK:
                rec = STATE.setdefault("ping_in", {"external": 0, "self": 0})
                rec["wake"] = (rec.get("wake") or 0) + 1
            return self._send(204, "")
        if path in ("/t", "/tiny"):                  # ultra-compact one-line status
            with _LOCK:
                snap = json.loads(json.dumps(STATE))
            last = snap.get("last") or {}
            bits = []
            for nm in ("slotchain", "keepwarm"):
                if last.get(nm):
                    bits.append("%s@%s/rc%s" % (nm, (last[nm].get("at") or "")[11:19], last[nm].get("rc")))
            nxt = ""
            _slots = sorted(next_slots(), key=lambda x: x.get("in_minutes", 99999))   # soonest slot first
            if _slots:
                nm = _slots[0]["slot"].split()[0].lower()                             # malwa / iari / afo
                nxt = "%s+%dm" % (nm, _slots[0]["in_minutes"])
            cyc = snap.get("cycles") or {}
            line = "ok started=%s cyc=sc%s/kw%s err=%s %s next=%s\n" % (
                (snap.get("started") or "")[11:19], cyc.get("slotchain", 0), cyc.get("keepwarm", 0),
                len(snap.get("last_error") or {}), " ".join(bits), nxt)
            return self._send(200, line)
        if path == "/":
            with _LOCK:
                snap = json.loads(json.dumps(STATE))
            snap["now_ist"] = istnow().isoformat(timespec="seconds")
            snap["next_slots"] = next_slots()
            for k in ("window", "host", "logs", "log"):
                snap.pop(k, None)                     # keep the body tiny: some free monitors reject large responses
            for k, v in list((snap.get("ping_in") or {}).items()):
                if isinstance(v, dict):
                    v.pop("ua", None); v.pop("ip", None)
            return self._send(200, json.dumps(snap, indent=1, default=str), "application/json")
        if path.startswith("/run/"):
            cmd = path.split("/")[-1]
            key = ""
            if "?" in self.path:
                for kv in self.path.split("?", 1)[1].split("&"):
                    if kv.startswith("key="):
                        key = kv[4:]
            if not ADMIN_KEY or key != ADMIN_KEY:
                return self._send(403, "forbidden\n")
            if cmd in ("slotchain", "keepwarm", "guard", "supply", "status"):
                threading.Thread(target=run_cycle, args=(cmd, [cmd]), daemon=True).start()
                return self._send(200, "started %s\n" % cmd)
            return self._send(400, "unknown command\n")
        return self._send(404, "not found\n")


def next_slots():
    """Human-readable countdown to the next test, for the status page."""
    now = istnow()
    out = []
    for label, hh, mm in (("MALWA 11:00", 11, 0), ("IARI 14:30", 14, 30), ("AFO 18:00", 18, 0)):
        t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if t < now:
            t += dt.timedelta(days=1)
        out.append({"slot": label, "in_minutes": int((t - now).total_seconds() // 60)})
    return out


def self_ping():
    """Keep the free instance awake by requesting our own /ping through the public URL.
    Harmless while we are asleep-proof: the request just hits the /ping handler and returns."""
    if not SELF_PING_URL:
        return
    time.sleep(40)                              # let the HTTP server bind first
    while True:
        rec = {"at": istnow().isoformat(timespec="seconds")}
        try:
            t0 = time.time()
            req = urllib.request.Request(SELF_PING_URL, headers={"User-Agent": "agri-selfping/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                code = r.status
                r.read(16)
            rec.update({"http": code, "secs": round(time.time() - t0, 2)})
        except Exception as e:
            rec["error"] = str(e)[:160]
        with _LOCK:
            STATE["self_ping"] = rec
        time.sleep(SELF_PING_SECS)


def main():
    threading.Thread(target=scheduler, daemon=True).start()
    if SELF_PING_URL:
        threading.Thread(target=self_ping, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("agri-quiz runner on 0.0.0.0:%d | host=%s | IST %s" % (
        PORT, STATE["host"], istnow().isoformat(timespec="seconds")), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
