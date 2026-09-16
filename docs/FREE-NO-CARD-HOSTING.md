# FREE + NO-CARD RUNNER — Render web service + free pinger (0 GitHub minutes, ₹0)

Oracle machine `cat > /dev/null` (card nahi chahiye nahi milta) — isliye ye plan:

```
        ┌─────────────── Render FREE Web Service (no card) ───────────────┐
        │  python3 engine/web.py                                          │
        │    GET /ping  ← cron-job.org (free) har 5 min ping  (neend nahi) │
        │    scheduler thread:                                            │
        │       har 60 s  (10:00–19:30 IST)  → engine.py slotchain        │
        │       har 3 min (24×7)             → engine.py keepwarm (desk)  │
        │       05:00 IST                    → engine.py supply           │
        │       22:00 IST                    → engine.py guard            │
        │       09:45 IST                    → git pull (code update)     │
        └─────────────────────────────────────────────────────────────────┘
   GitHub Actions: saare workflows DISABLED (code fallback ke liye repo me hai)
   state.json journal: engine khud repo me commit/push karta hai (push = free)
```

Render free plan me **credit card nahi maanga jaata**. (Agar kabhi maange → neeche "Plan B" dekho.)

---

## STEP 1 — Render par service banao (≈5 min)

1. https://render.com → **Get Started** → **GitHub** se sign up karo (email verify).
2. Dashboard → **New +** → **Web Service** → repo `b9811507-del/live-test` ko **Connect** karo
   (private repo ke liye Render ko permission dena hoga — "Configure account" → repo select).
3. Form me:
   | Field | Value |
   |---|---|
   | Name | `agri-quiz-runner` (jo mann kare) |
   | Region | Singapore (India ke najdeek) |
   | Branch | `main` |
   | Runtime | **Python 3** |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `python3 engine/web.py` |
   | Instance Type | **Free** |
4. **Environment** tab me ye variables daalo (Render dashboard me, encrypted rehte hain):

   | Key | Value |
   |---|---|
   | `TZ` | `Asia/Kolkata` |
   | `EXAM_TG_TOKEN` | exam bot ka token (@Arunkatyanquiz_bot) |
   | `CHAT_ID` | `-1003784795446` |
   | `IARI_CHAT` | `-1003922097468` |
   | `ADMIN_CHAT` | aapki DM chat id (alerts) |
   | `MONGO_URI` | Atlas connection string |
   | `GITHUB_TOKEN` | PAT (repo par **Contents: Read & write**) — journal push + code pull |
   | `GITHUB_REPOSITORY` | `b9811507-del/live-test` |
   | `RAZORPAY_KEY_ID` | Razorpay key id |
   | `RAZORPAY_KEY_SECRET` | Razorpay secret |
   | `PAID_CHAT_AFO` / `PAID_CHAT_PASHU` / `PAID_CHAT_CANE` | paid groups ke chat ids |
   | `PAID_PRICE_AFO` / `PAID_PRICE_PASHU` / `PAID_PRICE_CANE` | ₹251 / ₹151 / ₹151 |
   | `ADMIN_KEY` | koi bhi random string (manual `/run/...` trigger ke liye) |

   Optional (defaults admin-approved hain): `PAID_VERIFY=auto`, `POLL_MODE=quiz`,
   `PAID_SHOWCASE=off`, `REVEAL_AFTER_Q=off`, `CTA_SHOW=off`.

5. **Create Web Service** → pehla deploy ~2 min. Logs me ye dikhna chahiye:
   `agri-quiz runner on 0.0.0.0:10000 | host=agri-quiz-runner | IST …`

## STEP 2 — Service ko jaga rakho (free pinger, no card)

Render free service **15 min traffic ke bina so jaati hai**. Isliye:

1. https://cron-job.org → sign up (sirf email, **no card**).
2. **Create cronjob**:
   | Field | Value |
   |---|---|
   | Title | `agri-quiz keepawake` |
   | URL | `https://<your-service>.onrender.com/ping` |
   | Schedule | **Every 5 minutes** |
   | Save | ✔ |
3. (Optional) doosra cronjob: `https://<service>.onrender.com/` har 15 min — status snapshot dekhne ke liye.

Bas — 24×7 jagta rahega aur tests apne aap chalenge. **GitHub par 0 minutes.**

## STEP 3 — Verify (2 minute)

```bash
curl https://<your-service>.onrender.com/            # status JSON: cycles, last runs, next slot
curl https://<your-service>.onrender.com/ping        # ok
curl "https://<your-service>.onrender.com/run/status?key=<ADMIN_KEY>"
```
Status JSON me `cycles` badhte dikhne chahiye (`slotchain`, `keepwarm`) aur `next_slots` me agla test.

---

## Plan B (agar Render card maange, ya band ho jaye)

| Host | Card? | Port | Notes |
|---|---|---|---|
| **Hugging Face Spaces (Docker, free)** | ❌ nahi | **7860** | `PORT=7860`, Dockerfile: `FROM python:3.12-slim` + `pip install -r requirements.txt` + `CMD python3 engine/web.py`; Space **public** hoga (code dikhega), ping wahi cron-job.org se. Free Space 48 ghante inactivity par sota hai → pinger zaroori. |
| **Replit (free)** | ❌ nahi | 8080 | `python3 engine/web.py`, Always-On paid hai — free me bhi pinger se chal jayega |
| **PythonAnywhere (free)** | ❌ nahi | — | 1 daily scheduled task milta hai (kaam chalau), always-on tasks paid |
| **Purana Android phone / PC + Termux** | ❌ nahi | 8080 | `pkg install python git && … && python3 engine/web.py` — ghar par padha phone hi server |
| **GitHub Actions on a PUBLIC repo** | ❌ nahi | — | Sabse simple: repo public karo → Actions **unlimited free** → workflows enable karke wahi purana chain chalao (student data public ho jayega, isliye ise last option rakha hai) |

## Ye kya use nahi karta (jaan-boojh kar)

- **Oracle Cloud / AWS / GCP / Azure** — card verification chahiye → skip
- **Render ke paid instances** — paisa lagta hai → sirf Free instance use karna hai
- **GitHub Actions (private repo)** — minutes paid hain → workflows disabled, sirf backup ke liye rakhe hain
