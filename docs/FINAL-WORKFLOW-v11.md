# AGRI QUIZ DAILY EXAM SYSTEM v11.4 — COMPLETE WORKFLOW

> **v11.4 (admin order, 15-Sep evening)** — (a) **no paid-batches message or link in any group**
> (`PAID_SHOWCASE` is off by default; the enrolment code stays in the desk/DM path only);
> (b) after **every** 30 s question window a **reveal** is posted: correct option + the sheet's
> explanation + the names of who was right / wrong; (c) the result file carries **only the most
> recent test**; (d) the announce goes out at **exactly 11:00:00 / 14:30:00 / 18:00:00 IST** (no 2-min
> lead) → 15 s countdown → test → leaderboard → **TOP 3 toppers** → result file → **tomorrow's plan**;
> (e) the plan after 11:00 / 14:30 = next day's **page numbers**, after 18:00 = the **whole next-day
> schedule**; (f) **fresh Day 1 from 16-Sep**: book page 1, **3 pages/day** for iari (was 5), and the
> book now **continues across days** instead of restarting every morning (`series_reset` marker).
> Battery: **26/26 green**.
### Full setup, day-cycle, group display, failure handling and final output

---

## 0. THE WHOLE THING IN ONE PICTURE

```
                    ┌─────────────────────── GitHub (private repo: b9811507-del/live-test) ───────────────────────┐
                    │                                                                                              │
   Sources          │   WORKFLOWS (no server — every step runs on a GitHub runner)                                 │
 (read-only)        │                                                                                              │
                    │   slot-chain.yml      ← the dispatcher: runs every slot, then re-arms itself                 │
 6 Google Sheets ───┼──▶  slot-guard.yml   ← watchdog: revives a dead chain, DMs the admin only when needed          │
 (malwa vol1/vol2/  │   keepwarm-agent.yml  ← Render ping + maintenance + STUDENT DESK (DMs / payments / links)     │
  horti, iari)      │   afo-supply.yml      ← daily 05:00 IST AFO bank audit (never posts to Telegram)              │
                    │   slot-kill.yml       ← emergency stop (manual dispatch only)                                │
 MongoDB Atlas ─────┼──▶  booksend.yml     ← one-off book-file delivery (manual dispatch only)                    │
 (AFO bank 50 sets) │                                                                                              │
                    │   state.json  ← THE ONLY DATABASE (git journal, committed by the runners)                    │
                    └───────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                            │ Telegram Bot API (bot @Arunkatyanquiz_bot)
                                                            ▼
        ┌───────────────────────────────┬──────────────────────────────────────┬───────────────────────────────┐
        │  @agriquizworld -1003784795446│  student's private chat (chat box)   │  admin DM (ADMIN_CHAT)        │
        │  all 3 daily tests (locked)   │  /start → pay → JOIN LINK            │  alerts only, English         │
        └───────────────────────────────┴──────────────────────────────────────┴───────────────────────────────┘
```
**No Render / no server needed for anything except the existing paid-bot page (suspended, untouched).**

---

## 1. WHAT RUNS WHEN (heartbeat of the system)

| Workflow | Trigger | Cadence | Job timeout | What it does | What it NEVER does |
|---|---|---|---|---|---|
| **slot-chain** | self-dispatch + cron `*/10` (fallback) | self-chained, jitter **100–190 s** | 240 min | gate the 3 slots → announce (exact time) → 15 s countdown → polls **+ a reveal after each** → leaderboard → **top 3** → result file (latest test only) → **tomorrow's plan**; then re-arms itself | never cancel-in-progress, never retro-fires a missed slot, **never posts paid-batch messages** |
| **slot-guard** | self-dispatch + cron `*/15` | self-chained **~7 min** | 30 min | if no chain run is live and the last one is older than 25 min while a slot is still actionable → force-dispatch chain + DM admin | silent outside the daily window (no false alarms) |
| **keepwarm-agent** | self-dispatch + cron `*/10` | self-chained, throttled **~150 s** | 25 min | Render keepwarm ping · journal/agent maintenance · **student desk**: DMs, payment claims, invoice callbacks, single-use join links, join-request approvals · relay marker | never calls getUpdates while a test is live (no 409) |
| **afo-supply** | cron `30 23 * * *` = **05:00 IST** | daily | 45 min | AFO bank audit: coverage 13-Sep→1-Nov, no-repeat uid check, gap-fill if a pool exists | **never posts to Telegram** |
| **slot-kill** | **manual dispatch only** | on demand | 20 min | cancel chain+guard runs → 15 s grace → `git reset --hard origin/main` → seal every open job `step 8 + killed` → push → DM admin | push trigger only registers the file; the job skips on push |
| **booksend** | **manual dispatch only** | one-off | 350 min | send book MCQ files (page range, N pages/file) to the IARI group, pin every file, INDEX last with tap-jump links + ◀️Prev/📚Index/Next▶️ nav | never auto-fires |

---

## 2. THE DAY (all times IST — nothing happens outside these windows)

| IST | Event |
|---|---|
| **05:00** | `afo-supply` audits the Mongo AFO bank (50 sets, 13-Sep → 1-Nov, zero repeated questions). Silent. |
| 24 × 7 | `keepwarm-agent` every ~150 s: Render ping + **student desk** — students can enrol any time of day; links are issued within ~2.5 min of a claim. |
| **10:10** | malwa window opens (go − 50 min). Chain starts running the job. |
| **10:10** | the runner waits silently (heartbeat only, **zero group traffic**) |
| **11:00:00 sharp** | **ANNOUNCE** posted + **pinned** (v11.4: no lead). Previous announce of any earlier test is auto-unpinned here → exactly one pin. |
| **11:00:00 + 0–15 s** | **15-second countdown** on the same pinned message: `Starting in 15s… 10s… 5s… 3s… 2s… 1s… Starting now — good luck!` |
| **11:00:15** | **20 polls**, one open at a time, each **30 s auto-close**; votes counted live; **reveal after each poll** (correct option + explanation + right/wrong names). |
| ~11:11 | **Leaderboard** (≤48 rows/msg, medal + tap-able name) → **TOP 3 toppers** → **result file** (HTML, latest test only) → **tomorrow's plan** (next day's page numbers) → one-line sign-off. **No paid-batches message (v11.4).** |
| 11:15 | malwa slot sealed `step 8`. Volume rollover happens automatically when a book is exhausted (VOL 1 → VOL 2 → HORTICULTURE → series-complete message + slot closes). |
| **13:40** | iari window opens. |
| **14:30:00 sharp** | **ANNOUNCE** pinned (malwa's announce unpinned → still exactly **one** pin). |
| **14:30 + 15 s** | countdown → **all questions of the next 3 book pages** (v11.4, was 5; N = actual count — real book: day 1 = pages 2,4,5 = 35 Q ≈ 18 min), +1 / −0.25. |
| **17:10** | AFO window opens. |
| **18:00:00 sharp** | **ANNOUNCE** pinned (no lead). |
| **18:00** | 15 s countdown → **50 Q full-length**, +2 / −0.5, from that IST day's Mongo set. |
| ~18:27 | leaderboard → **top 3** → result file → **tomorrow's full schedule** (malwa pages + iari pages + AFO set). Mongo set marked `used`, uids booked in the no-repeat ledger. No paid message. |
| 22:00 | Any slot still unfinished is **sealed missed** (+1 admin DM). After this it can never fire today. |
| **Miss rule** | A slot that passes **go + 4 h** is sealed `missed` forever — no retro-fire, no stale announcement. |

---

## 3. WHAT THE GROUP ACTUALLY SHOWS (one test, top to bottom)

```
── @agriquizworld ──────────────────────────────────────────────────────────────
📌 ☀️ MALWA BOOK VOL 1                          ← PINNED (and the ONLY pinned message)
   📅 16 September 2026 · ⏰ 11:00 AM IST
   📖 Book pages 1-6
   📝 20 questions · 30 seconds each · one answer, poll auto-closes
   🏆 +1 correct · −0.25 incorrect · leaderboard & result file at the end 📄
      (same message edits to) ⏳ Starting in 15s… → Starting now — good luck!

1/20. [General Agriculture] The word "agriculture" is derived from…
   A) Ager + Cultura   B) Agro + Cultus   C) Agric + Utura   D) Agro + Cultura   E) None of these
      → poll closes automatically after 30 s, next one follows immediately (×20)

🏆 MALWA BOOK VOL 1 — LEADERBOARD (20 questions · +1 / −0.25)
   🥇 Ravi Meena — +18.8 · 19 correct · 1 incorrect
   🥈 Sunita Devi — +16.5 · 18 correct · 6 incorrect
   🥉 Mohan Lal — +14.2 · 15 correct · 3 incorrect
   #12. Pooja Sharma — +6.0 · 7 correct · 4 incorrect

📖 Tomorrow (17 September 2026): MALWA BOOK VOL 1 — book pages 5-14      ← chhota note

🎉 MALWA BOOK VOL 1 completed — 20 questions, thank you all for participating! 🌾
   🥇 Top scorer: Ravi Meena — +18.8                                     ← NOT pinned

📄 MALWA_BOOK_VOL_1_2026-09-16_results.html      ← document (scores + answer key), NOT pinned
🌾 Daily schedule: 11:00 AM Malwa Book · 2:30 PM IARI Book · 6:00 PM AFO Mains — @agriquizworld

🎓 PAID BATCHES — ENROLMENT OPEN                                          ← LAST message
   🌆 AFO MAINS BATCH 2026 — ₹___      Full-length tests · practice · PDF notes
   🐄 PASHUDHAN ADHIKARI BATCH — ₹151  Classes · daily tests · notes
   🎋 SUGARCANE PREMIUM BATCH — ₹151   Premium classes · daily tests · notes
   [🌆 Enrol] [🐄 Enrol ₹151] [🎋 Enrol ₹151] [📋 All batches]            ← buttons
── end of one test (19 messages for malwa, 57 for iari-56Q, 51 for AFO-50Q) ────
```
**Pinning rule:** exactly ONE pinned message at any time = the announce of the current test. The result file is **never** pinned.

---

## 4. STUDENT ENROLMENT — what happens in the student's own chat box

```
Group button  →  opens bot DM (/start buy_afo)
      │
      ▼
👋 Welcome to AGRI QUIZ WORLD
🌆 AFO MAINS BATCH 2026 — ₹___
   Full-length AFO mains tests · subject-wise practice · PDF notes · doubt support
   1) Tap Pay securely  2) Return and tap "I have paid"  3) Your one-time join link arrives here
   [ 💳 Pay securely ]   [ ✅ I have paid ]
      │                                   │
      │ (Telegram Payments token set)     │ (external link / UPI)
      ▼                                   ▼
instant verification                 claim recorded → admin alerted
createChatInviteLink(member_limit=1, 24 h)
      │
      ▼
🎉 Enrolment confirmed — AFO MAINS BATCH 2026
   Your personal one-time join link: https://t.me/+XXXXXXXX
   [ 🚀 Join AFO MAINS BATCH 2026 ]
      │
      ▼
/reissue anytime → /mybatches → fresh link      (+ auto link re-issue if it had failed earlier)
```
Admin side: `/admin <KEY> pending | stats | approve <uid> <batch> | link <uid> <batch> | revoke <uid> <batch>` (DM only, key from the `ADMIN_KEY` secret).

---

## 5. ADMIN ALERTS (private DM, English, rate-limited)

| Alert | When |
|---|---|
| `⛔ <job> could not start` | bot lacks Post/Pin rights in the group (with the exact fix) |
| `⚠️ <job> slot missed` | slot crossed go + 4 h and was sealed |
| `🛡 slot-guard … revived` | chain was stale > 25 min and got force-restarted |
| `❗️ <job> cycle error` | a job raised (other two still ran — isolated) |
| `💳 New enrolment …` | student paid; batch, student id, mode, link issued |
| `⚠️ Cannot create a join link for <batch>` | bot not admin-with-Invite-Users in that batch group |
| `🧾 Payment reference …` | student sent a UTR/reference |

---

## 6. STATE, CRASH-RESUME AND SAFETY (why nothing duplicates)

* **Journal = `state.json` in git.** `days[IST-date][job]` with `step` (1 announced → 2 polls running → 3 polls done → 4 leaderboard → 8 complete), `qidx`, per-question answers, `plan` (the frozen paper), message ids.
* **Frozen paper:** the day's questions are read once at window-open and stored → a mid-day sheet edit can never change a running exam.
* **Resume, never duplicate:** a per-question “claim” (`sent_i`) is written *before* `sendPoll`; `msg_ann`, `lb_sent`, `congrats_sent`, `file_sent`, `cta_sent`, `paid_msg`, `tmr_note` are journaled — a crashed run continues exactly where it stopped and **never re-announces**.
* **Two runners can't double-run a test:** lock (`locked_by` + heartbeat ≤ 120 s) per job; state pushes merge by max(step, qidx) with rebase-retry.
* **Single Telegram poller at a time:** the exam loop drains `getUpdates` during polls; the student desk **skips its poll** while any test is live (battery case 15 proves `getUpdates calls=0`) → no `409 Conflict`.
* **Rights gate:** before any announce the engine checks `getChatMember`; if the bot is not admin it does **not** post anything and DMs the admin (battery case 11).
* **Emergency stop:** `slot-kill` cancels chain+guard, seals all open jobs, pushes, DMs.
* **Journal growth:** above 700 KB the push switches to the Git-Data API (blobs/trees), so the ~70 KB/day journal can never break the 1 MB Contents-API limit.
* **Deletion policy:** nothing is deleted — no group messages, no Mongo sets, no journal history (`kuch delete n ho`). Missed AFO days release their bank set back to `ready` (unused).

---

## 7. RUNNER-OUTPUT / DELIVERABLES (the “final output”)

**Repo `b9811507-del/live-test@main`**
```
engine/engine.py     engine/builder.py    engine/afo_mongo.py    engine/translator.py   engine/paid.py
agents/relay.py      agents/kill.py
.github/workflows/   slot-chain · slot-guard · keepwarm-agent · afo-supply · slot-kill · booksend
state.json           (journal: 13-Sep / 14-Sep history + today, sealed 15-Sep malwa, live iari+afo)
tests/               verify_all.py · fake_clock.py · fixtures · render_preview.py · make_fixtures.py
docs/                LOCK-V11.md · BUILD-REPORT-v11.md · BUILD-REPORT-v11.1.md (includes v11.2) · GROUP-MESSAGES-EN.md
```
**Group output per test (v11.4):** announce (pinned, at the exact slot time) → 15 s countdown → N polls, each followed by a reveal → leaderboard → top 3 toppers (bold, extra spacing) → HTML result file (that test only) → tomorrow's plan (pages after 11:00/14:30, full schedule after 18:00). **No paid-batches message anywhere.**
**Result file:** `out/<LABEL>_<DATE>_results.html` — score table (rank, name, net, correct, incorrect, skipped) + answer key + question-wise view with the correct option ticked and what the player picked. Preview: `SAMPLE-result-EN.html`.

**Verification (re-runnable any time):** `python3 tests/verify_all.py` → **GATE RESULT: GREEN**, fake-clock battery **16/16**
```
idle · warm window (announce+countdown+20Q) · multi-window/defer · missed-after-4h · resume-mid-polls ·
step≥8 skip · afo closed after last day · one-job error isolated · exact 14:30 boundary ·
afo next-day advance · bot-not-admin blocked · booksend smoke · enrolment claim → single-use link ·
invoice → auto link · desk silent while live · single pin handover
```

---

## 8. WHAT YOU STILL NEED TO DO (only these; everything else is automated)

| # | Action | Why | Blocks |
|---|---|---|---|
| 1 | Add **@Arunkatyanquiz_bot as admin** in @agriquizworld (Post + Pin + Delete) | live gate shows `status=member`, group is admins-only | **all 3 daily tests** |
| 2 | Secrets `PAID_LINK_AFO`, `PAID_LINK_PASHU`, `PAID_LINK_CANE` | buttons then go straight to your payment page | direct payment buttons |
| 3 | Secret `PAID_PRICE_AFO` | AFO price in the showcase | AFO button label |
| 4 | Correct **PASHUDHAN chat id** → `PAID_CHAT_PASHU` (spec value `-10033947957354` = `chat not found`) | join links for that batch | Pashudhan links |
| 5 | Optional: `PAY_PROVIDER_TOKEN` (BotFather → Payments) | instant automatic verification instead of the "I have paid" tap | instant links |
| 6 | Optional: fix the `CHAT_ID` secret (currently ≠ locked group; engine already forces the locked id) | removes the warning | nothing |

**Manual commands (only if you want to intervene)**
```
Actions → slot-chain → Run workflow            # run a cycle now
python3 engine/engine.py status                # what is scheduled / sealed / done
python3 engine/engine.py ready                 # rights gate (group + 3 batch groups)
python3 engine/engine.py run iari              # force one job (debug)
python3 engine/engine.py translate "<text>"    # check the translator
python3 engine/engine.py paid text             # preview the paid-batches message
Actions → slot-kill → Run workflow             # EMERGENCY STOP
Actions → booksend → Run workflow              # book delivery (job, range, step, chat)
```

---

## 9. TODAY (15-Sep) — live status right now

| Slot | Status |
|---|---|
| 11:00 malwa | **sealed** by your order (chain logs `phase=done step=8`) |
| 14:30 iari | waiting — `phase=idle step=0`; window closes **18:30**. Will run 56 Q (pages 2, 4, 5, 7, 8) the moment the bot has rights |
| 18:00 afo | waiting — set_no 3 (50 Q) ready; window closes **22:00** |
| Chain | alive, self-chaining, re-armed as `no further cycle needed today` until a slot's window opens |
| Student desk | running (journal `desk: {offset, last}`), no pending claims yet |
