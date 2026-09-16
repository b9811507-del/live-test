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

## IMPORTANT — Render auto-deploy OFF (16-Sep fix)
Engine har cycle ke baad `state.json` journal ko main par push karta hai (~1-3 min me ek commit).
Render ka **autoDeploy** un commits par bhi build chalu kar deta tha → instance har ~7 min restart
(observed starts: 12:36, 12:44, 12:51, 12:58). Pending deploys cancel/niptane ke baad:

```bash
# autoDeploy off (ek hi baar)
curl -X PATCH -H "Authorization: Bearer $RENDER_KEY" -H "Content-Type: application/json" \
  -d '{"autoDeploy":"no"}' https://api.render.com/v1/services/srv-dal3nhn40ujc739eevng
```
Ab **code push karne par runner apne aap update nahi hoga** — deploy manually:
```bash
curl -X POST -H "Authorization: Bearer $RENDER_KEY" -H "Content-Type: application/json" -d '{}' \
  https://api.render.com/v1/services/srv-dal3nhn40ujc739eevng/deploys
```
Rules: (1) test ke ±10 min me deploy/push mat karo (14:30 IARI, 18:00 AFO) — restart cycle ko beech me kaat deta hai;
(2) journal commits ab bilkul harmless hain, wo test ke beech me bhi aate rahenge.

## Response-size safe endpoints (kuch monitors bade response reject karte hain)
| Endpoint | Size | Kab use karein |
|---|---|---|
| `/ping` | **3 bytes** (`ok`) | **default — yahi use karo** |
| `/wake` | **0 bytes** (HTTP 204) | agar monitor "response too large" ya khaali body maange |
| `/t` | ~150 bytes one-line | chhota status: `ok started=13:33 cyc=sc12/kw5 err=0 slotchain@13:45:02/rc0 next=iari+56m` |
| `/` | ~0.4 KB JSON | detailed status (machines) |
Repo/ dashboard / GitHub API URLs **mat** de dena monitor ko — wo bade HTML/JSON dete hain aur wahi "output too large" wali error aati hai.
