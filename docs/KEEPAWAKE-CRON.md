# KEEP-AWAKE CRON — runner ko 24x7 jagaye rakhna (₹0, koi card nahi)

Render free web service **15 minute** bina traffic ke sone jati hai. Isliye ek **bahar wala pinger** chahiye.
Runner: `https://live-test-8wu1.onrender.com` — `/ping` pe koi response parse karne ki zaroorat nahi, sirf hit hona chahiye (HTTP 200 = ok).

## Layer 0 (PRIMARY, built into the runner) — self-ping
`engine/web.py` khud ko har **4 minute** me apne public URL `…/ping` par request karta hai (thread `self_ping`).
Free host ki "15 min bina traffic = so jao" condition isse kabhi poori nahi hoti — **koi bahar ka pinger,
koi GitHub minute, koi account ki zaroorat nahi**. Status page `/` me `self_ping` field live rehta hai:
```json
"self_ping": {"at": "2026-09-16T12:46:27+05:30", "http": 200, "secs": 0.7}
```
Band karna ho to Render env var `SELF_PING_URL=` (empty) set kar dena. Interval badalna ho to `SELF_PING_SECS`.

## Layer 1 — GitHub cron (lagaya hua hai, par is account par fire nahi ho raha)
Repo: https://github.com/b9811507-del/agri-quiz-keepawake — workflow `keepawake` (cron `*/5` + offset list ≈ 2.5 min).
Public repo = free unlimited Actions minutes. Push-event runs **success** hote hain, lekin **scheduled runs aa hi nahi rahe**
(16-Sep 14+ minute observe, `event=schedule` count = 0) — account-level Actions block ki wajah se.
Rakha hua hai: agar GitHub theek ho jaye to apne aap kaam karega. Iske bharose test na chhodo.

## Layer 2 (RECOMMENDED) — cron-job.org (purpose-built cron, email signup, koi card nahi)
1. https://cron-job.org/en/signup/ → email + password (verify email link).
2. Login → **Create cronjob**:
   * Title: `agri-quiz-runner`
   * URL: `https://live-test-8wu1.onrender.com/ping`
   * Schedule: **Every 5 minutes** (Preset → Every 5 minutes)
   * Save → toggle **Enabled**. (Optional: "Save responses in history" ON taaki log dikhe.)
3. 10 minute baad **History** tab me HTTP 200 dikhna chahiye.
   Free plan: unlimited jobs, 1-minute interval tak, response-history limit chhota hota hai — kaafi hai.

## Layer 2-alt — Google Apps Script (koi naya account hi nahi; aapke Google login se)
File: `tools/keepawake_appsscript.gs` (script.google.com me paste karna hai) — steps us file ke top par likhe hain.
Trigger: `keepAwake` → Time-driven → Minutes timer → **Every 5 minutes**. Executions log me `ping=200 cycles=... errors=none` dikhega.

## Verify (kabhi bhi)
```bash
bash deploy/check_runner.sh https://live-test-8wu1.onrender.com <ADMIN_KEY>
```
Expected: `status: ok`, `slotchain` fresh (≤3 min purana, 10:00–19:30 IST me), `errors: none`.
Render dashboard → live-test → Logs me engine output bhi mirror hota hai.

## Notes
* Sirf **ek** hi Render service ko ping karo (`live-test`) — free plan 750 instance-hours/month account-wide deta hai; baaki 3 services suspended hain, unhe chhedna nahi.
* Pinger se instance-hour **kharch nahi badhta** (jagta to pura month hi tha) — 24x7 = 744 h/month, budget ke andar.
* Ye pinger sirf awaking karta hai; test ka time, announce, polls — sab runner ke andar ka scheduler karta hai.
