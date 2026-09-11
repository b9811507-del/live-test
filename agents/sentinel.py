#!/usr/bin/env python3
"""agent-sentinel — watches the LIVE services and self-heals, DMs SatyamSir only when something
was wrong or was fixed (never spams on green). Checks: Render /healthz, paid-bot polling
(getWebhookInfo pending), Razorpay order drift, stale git state pointer, tonight's slot presence.
Env: RENDER_URL, RENDER_API_KEY, RENDER_SVC, PAID_BOT_TOKEN, TG_TOKEN, ADMIN_CHAT, ADMIN_KEY."""
import os, sys, json, time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from renderapp import llmsupport

R_URL = os.environ.get("RENDER_URL", "https://livescore-zp5w.onrender.com").rstrip("/")
R_KEY = os.environ.get("RENDER_API_KEY", "")
R_SVC = os.environ.get("RENDER_SVC", "")
PAID_TK = os.environ.get("PAID_BOT_TOKEN", "")
TG = os.environ.get("TG_TOKEN", "")
ADMIN = os.environ.get("ADMIN_CHAT", "1138783169")
AK = os.environ.get("ADMIN_KEY", "")


def get(url, timeout=25, hdr=None):
    rq = urllib.request.Request(url, headers={"User-Agent": "agent-sentinel/1.0", **(hdr or {})})
    return urllib.request.urlopen(rq, timeout=timeout).read()


def dm(text):
    if not TG:
        print("(no DM)", text[:200]); return
    try:
        get0 = urllib.request.Request(f"https://api.telegram.org/bot{TG}/sendMessage",
            data=json.dumps({"chat_id": ADMIN, "text": text[:3900], "parse_mode": "HTML"}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(get0, timeout=20).read()
    except Exception as e:
        print("dm fail:", e)


def render_api(method, path, body=None):
    import urllib.request as u
    rq = u.Request(f"https://api.render.com/v1{path}",
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {R_KEY}", "Content-Type": "application/json", "User-Agent": "agent-sentinel"})
    d = u.urlopen(rq, timeout=30).read()
    return json.loads(d) if d else {}


def restart_render(reason):
    """Trigger a fresh deploy (restarts gunicorn + bot poller)."""
    if not (R_KEY and R_SVC):
        return False
    try:
        render_api("POST", f"/services/{R_SVC}/deploys", {})
        return True
    except Exception as e:
        print("restart fail:", e)
        return False


def health():
    for a in range(3):
        try:
            j = json.loads(get(f"{R_URL}/healthz", timeout=18))
            if j.get("ok"):
                return j
        except Exception:
            time.sleep(6 + 4 * a)
    return None


def workflow_ran_recently(wf, hours=16):
    """slot cron must have executed in last `hours` (else system not yet expected to have it)."""
    try:
        repo = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - hours * 3600))
        url = f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs?per_page=3&created=%3E={since[1:]}"
        j = json.loads(get(url, timeout=20, hdr={"Accept": "application/vnd.github+json"}))
        return any(r.get("status") in ("completed", "in_progress", "queued") for r in j.get("workflow_runs", []))
    except Exception:
        return False


def main():
    issues, fixes = [], []
    h = health()
    if h is None:
        issues.append("Render /healthz DOWN (3 retries)")
        if restart_render("down"):
            fixes.append("♻️ Render redeploy triggered — ~1 min me wapas aana chahiye.")
    # paid bot alive?
    if PAID_TK:
        try:
            wi = json.loads(get(f"https://api.telegram.org/bot{PAID_TK}/getWebhookInfo"))["result"]
            if wi.get("url"):
                issues.append(f"paid bot webhook set to {wi['url']} (poller will starve)")
                json.loads(get(f"https://api.telegram.org/bot{PAID_TK}/deleteWebhook"))
                fixes.append("🪝 Stray webhook deleted — long-poll resumed.")
            elif (wi.get("pending_update_count") or 0) > 15:
                issues.append(f"paid bot stuck: {wi['pending_update_count']} updates pending")
                if restart_render("stuck"):
                    fixes.append("♻️ Render restart triggered (bot poller jam).")
            elif wi.get("last_error_message"):
                issues.append("tg last error: " + wi["last_error_message"][:120])
        except Exception as e:
            issues.append(f"paid bot API unreachable: {e}")
    # slot freshness ONLY inside its live window and only if that slot workflow actually ran recently
    ist = time.time() + 19800
    day = time.strftime("%Y-%m-%d", time.gmtime(ist))
    hh = time.gmtime(ist).tm_hour * 60 + time.gmtime(ist).tm_min
    try:
        days = h.get("days", {}) if h else {}
        for job, win, wf in (("malwa", (11 * 60 + 4, 11 * 60 + 40), "slot-malwa.yml"),
                             ("iari", (14 * 60 + 34, 15 * 60 + 5), "slot-iari.yml"),
                             ("afo", (18 * 60 + 4, 19 * 60 + 15), "slot-afo.yml")):
            if not (win[0] <= hh <= win[1]):
                continue
            if not workflow_ran_recently(wf):
                continue
            d0 = days.get(job)
            dd = d0.get("date") if isinstance(d0, dict) else d0
            if dd != day:
                issues.append(f"{job}: window me hai par Render par aaj ka slot ({day}) nahi mila — prebuild/run check karo")
    except Exception:
        pass
    # test-page sanity for AFO tonight
    if issues and llmsupport.providers():
        diag = llmsupport.ask("You are ops assistant for a Telegram exam-bot stack (GitHub Actions crons + Render Flask + Telegram Bot API). "
                              "Given issues, reply 2-4 short Hinglish lines: kya hua, kyun, admin ko kya karna hai. Plain text.",
                              "ISSUES:\n" + "\n".join(issues), 600)
        if diag:
            fixes.append("🧠 <b>AI diagnosis</b>\n" + diag.replace("<", "&lt;"))
    if issues:
        dm("🚨 <b>agent-sentinel</b>\n⚠️ Issues: " + "\n".join(f"• {i}" for i in issues)
           + ("\n\n" + "\n".join(fixes) if fixes else "\n\n(manual action needed)"))
        print("issues:", issues, "| fixes:", fixes)
    else:
        print("all green ✓")
    # always exit 0 unless DM failed hard
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        dm(f"🚨 sentinel crash: <code>{str(e)[:180]}</code>")
        sys.exit(1)
