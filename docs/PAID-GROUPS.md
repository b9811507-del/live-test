# PAID BATCHES — verified status (2026-09-15, live Telegram API)

| Batch | Price | Chat id | Group title | Bot status |
|---|---|---|---|---|
| IARI BOOK MCQ BATCH | ₹99 | `-1003922097468` | IARI BOOK | administrator ✓ (invite+pin) — promoted 15-Sep |
| MALWA BOOK VOL 1+2+HORTICULTURE | ₹151 | `-1003761821341` | Malwa Book Quiz | administrator ✓ (invite+pin) — promoted 15-Sep |
| NEMRAJ SUNDA BOOK BATCH | ₹99 | `-1003853396327` | Nemraj Sunda Quiz | administrator ✓ (invite+pin) — promoted 15-Sep |
| RK SHARMA BOOK BATCH | ₹99 | `-1003880198347` | RK sharma Quiz | administrator ✓ (invite+pin) — promoted 15-Sep |
| AFO SELECTION BATCH | ₹251 | `-1003687531473` | AFO Selection Batch 2026 | administrator ✓ (invite+pin) |
| SUGARCANE PREMIUM BATCH | ₹151 | `-1003707610763` | SUGARCANE PREMIUM BATCH | administrator ✓ (invite+pin) |
| PASHUDHAN ADHIKARI BATCH | ₹151 | `-1003947957354` | PASHUDHAN PRASAR ADHIKARI | administrator ✓ (invite+pin) |

**Main test group** @agriquizworld `-1003784795446` — bot = **administrator** (Post ✓ Pin ✓ Delete ✓).

## Payment flow (v11.3, Razorpay — no webhook, no server)
1. Student taps a batch button in the group → opens the bot chat (`/start buy_<batch>`).
2. Bot shows the batch → **💳 Pay ₹X — Razorpay** → the bot **creates a personal Razorpay payment link**
   (`POST /v1/payment_links`, callback back to the bot).
3. Student pays (UPI/card/netbanking on Razorpay's page).
4. The keepwarm desk pass checks the link status every ~150 s (`GET /v1/payment_links/{id}`);
   on `status=paid` the bot creates a **single-use invite link** (`member_limit=1`, 24 h) and sends it
   into that student's chat — plus an enrolment DM to the admin.
5. Link expired? The student automatically gets a **fresh pay button**. Fallbacks kept: “I have paid”
   claim and Telegram-native invoices (if a provider token is ever added).

Secrets in use: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` (never logged/printed), `RAZORPAY_WEBHOOK_URL`
(stored for reference; **not required** — the old webhook host returns 503, which is why the design polls).
A ₹1 live-mode verification link was created during testing and **cancelled** immediately.

## Group pin policy
Exactly ONE pinned message in @agriquizworld = the announce of the current/next test. The paid-batches
message is the LAST message of each test and is **not** pinned; when a later test posts its own paid
message, the earlier one is deleted (one paid message per day, never two copies).
