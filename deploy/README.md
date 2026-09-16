# FREE RUNNER SETUP — always-on VM + cron (0 GitHub minutes)

GitHub Actions par private repo ke minutes **paid** hain (2,000 min/month free, hamara purana 24×7
self-chain ~3,000 min/day jala raha tha). Isliye scheduler **apni free VM ke cron par** shift kar
diya gaya hai:

```
                 ┌──────────────────────── FREE VM (always on) ────────────────────────┐
   Google Sheets │  cron (Asia/Kolkata)                                               │
   MongoDB ──────┼─▶ */1 10:00-19:30  run_cycle.sh slotchain   ← 11:00 / 14:30 / 18:00 tests│
   Telegram ─────┼─▶ */3 24×7         run_cycle.sh keepwarm    ← student desk + payments    │
                 │  05:00 daily       run_cycle.sh supply      ← AFO bank audit             │
                 │  22:00 daily       run_cycle.sh guard       ← safety net                 │
                 │  09:45 daily       update.sh                ← code auto-update          │
                 │  state.json  ⇄  git push/pull (journal)    ← push = free, koi minutes nahi│
                 └───────────────────────────────────────────────────────────────────────────┘
GitHub Actions: saare workflows DISABLED (fallback ke liye code wahin pada hai, chalta nahi).
```

---

## 0. CARD-FREE ROUTE (recommended — Render free web service)

Agar card nahi hai (Oracle/AWS/GCP sab card maangte hain) to **Render free Web Service + free pinger**
use karo — poora guide: **`docs/FREE-NO-CARD-HOSTING.md`**. Short me:

1. render.com → New Web Service → is repo ko connect → Runtime **Python 3**,
   Build `pip install -r requirements.txt`, Start `python3 engine/web.py`, Instance **Free**.
2. Dashboard → Environment me secrets daalo (`EXAM_TG_TOKEN`, `MONGO_URI`, `GITHUB_TOKEN`, `ADMIN_CHAT`,
   `RAZORPAY_*`, `PAID_CHAT_*`, `TZ=Asia/Kolkata`).
3. cron-job.org (free, no card) se `https://<service>.onrender.com/ping` har **5 min** ping karo —
   free instance 15 min traffic ke bina sota hai, pinger use jagaye rakhta hai.

`engine/web.py` khud hi wahi schedule chalata hai jo neeche cron file karti hai (tests 11:00/14:30/18:00,
desk har 3 min, supply 05:00, guard 22:00, code update 09:45). GitHub Actions saare **disabled** hain.

---

## 1. VM banao (agar card wala free VM available ho, e.g. Oracle Cloud Always Free)

1. **signup**: https://www.oracle.com/cloud/free/ → *Start for free* (card sirf verification ke liye,
   Always Free resources par charge nahi lagta; kabhi-kabhi card verify hota hai ~$1 hold ke saath).
2. Console → **Compute → Instances → Create instance**
   - Image: **Ubuntu 22.04** (ya 24.04)
   - Shape: **VM.Standard.E2.1.Micro** (x86, always free) **ya** VM.Standard.A1.Flex (ARM, always free)
   - Add SSH key (paste apni public key) → Create.
3. Public IP note kar lo (instance details me).
4. Login: `ssh ubuntu@<IP>` (Oracle Ubuntu image me user `ubuntu` hota hai; key ke saath).

*(Alternatives jo free hain: Google Cloud e2-micro free tier, ya apne ghar ka purana PC/Raspberry Pi.
Render free web service cron ke liye reliable nahi — sleep ho jaata hai.)*

## 2. Code + setup (VM par, 3 command)

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq git
sudo mkdir -p /opt/agri-quiz && sudo chown $USER /opt/agri-quiz
git clone https://<PAT>@github.com/b9811507-del/live-test.git /opt/agri-quiz
cd /opt/agri-quiz && bash deploy/vm_setup.sh
```

`vm_setup.sh` khud hi: python+pip+pymongo install karta hai, timezone IST karta hai,
`deploy/.env` banata hai, cron file `/etc/cron.d/agri-quiz` me daalta hai.

## 3. Secrets bharo (sirf 1 file)

```bash
nano /opt/agri-quiz/deploy/.env
```
Zaroori values:
- `EXAM_TG_TOKEN` — exam bot ka token (@Arunkatyanquiz_bot)
- `MONGO_URI` — AFO bank ka Atlas connection string
- `GITHUB_TOKEN` — PAT (repo par **Contents: Read & write**) → journal push ke liye (push free hai, minutes nahi lagte)
- `ADMIN_CHAT` — aapki DM chat id (alerts)
- `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` — payment links ke liye
- `PAID_CHAT_*` — paid batches ke group ids (docs/PAID-GROUPS.md me table hai)

## 4. Check karo

```bash
deploy/run_cycle.sh status            # journal dikhega
deploy/run_cycle.sh keepwarm          # ek desk pass
cat /etc/cron.d/agri-quiz             # cron lines
tail -f deploy/logs/slotchain.log     # live log
```
Sab theek ho to **11:00 / 14:30 / 18:00 IST** ke tests apne aap chalenge — koi GitHub run nahi.

## 5. Roz-marra ka kaam

| Kaam | Command |
|---|---|
| Code update | `deploy/update.sh` (cron 09:45 IST par khud bhi karta hai) |
| Journal dekho | `deploy/run_cycle.sh status` |
| Manual test (slot time par) | `deploy/run_cycle.sh slotchain` |
| Ek test force | `deploy/run_cycle.sh run malwa` (careful: live group me post karega) |
| Logs | `deploy/logs/*.log` (5 MB par rotate) |
| Cron band/on | `sudo rm /etc/cron.d/agri-quiz` / `bash deploy/vm_setup.sh` |

## 6. GitHub Actions (fallback, abhi OFF)

Workflows repo me hain (`slot-chain`, `slot-guard`, `keepwarm-agent`, `afo-supply`, `booksend`,
`slot-kill`) lekin **disabled** hain — accidental minutes burn na ho. Zaroorat pade to:

```bash
# on karne ke liye (dashboard): repo → Actions → workflow → "Enable workflow"
# ya CLI:  gh workflow enable slot-chain.yml
```
Aur jahan-jahan `*/10`, `*/15` cron the, woh **already hata diye gaye** hain (low-burn patch):
guard/keepwarm ab self-chain nahi karte, chain sirf 10:00–19:15 IST window me khud ko dobara
dispatch karta hai — agar kabhi GitHub par wapas chalao to bhi burn ~500 min/day rahega
(us par bhi billing/spending-limit sambhalna padega, isliye VM+cron hi asli free rasta hai).
