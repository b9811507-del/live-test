# AGRI QUIZ DAILY EXAM SYSTEM v11 — RECON + LOCK SHEET
_All evidence below is raw command output from this session. Nothing claimed that wasn't verified. Tokens/keys never printed._

---

## A. RECON RESULTS (verified)

| # | Check | Command essence | Verified result |
|---|---|---|---|
| A1 | PAT works, admin on repo | `GET /user`, `GET /repos/b9811507-del/live-test` | `login: b9811507-del`, repo `private: true`, `permissions.admin: true`, default branch `main` ✅ |
| A2 | Repo contents inherited | `git clone`, `find` | `SPEC.md` (T1–T5), `engine/afo18.py` (304 lines), `.github/workflows/afo-today.yml`, `state.json` (afo18 sealed `step:8, qidx:20, msg_ann:29092`) |
| A3 | Workflow states | `GET /actions/workflows` | only `357812225 afo-today.yml → disabled_manually` ✅ (everything stopped) |
| A4 | Live runs | `GET /actions/runs?status=in_progress|queued` | `in_progress: 0 []`, `queued: 0 []` ✅ nothing running |
| A5 | Secrets vault | `GET /actions/secrets` | **17 names, all present**, none missing: ADMIN_CHAT, ADMIN_KEY, CHAT_ID, EXAM_TG_TOKEN, GEMINI_API_KEY, GEMINI_API_KEY2, GROQ_API_KEY, IARI_CHAT, MISTRAL_API_KEY, MONGO_URI, OPENROUTER_API_KEY, PAID_BOT_TOKEN, PAID_TOKEN, RENDER_API_KEY, RENDER_SVC, RENDER_URL, TG_TOKEN ✅ (values unreadable by design — engine reads them at runtime only) |
| A6 | EXAM bot identity + webhook | `getMe`, `getWebhookInfo` | `Arunkatyanquiz_bot` ("Premium batch"), `url: ""`, `pending_update_count: 0` ✅ webhook deleted, no 409 risk |
| A7 | Mongo bank | `pymongo` on `MONGO_URI` | `agri` = `afo_sets, afo_supply, afo_used_q`; **50 sets, all `status: ready`**, dates `2026-09-13 → 2026-11-01`, 50 Q each, q fields `{uid,q,o[5],key}`; `afo_supply.next_set_no: 50`; `afo_used_q: 2500` (all `used_on: None` = reservation ledger); uid overlap between consecutive sets **0** ✅ |
| A8 | Sheet readers | `curl -sL .../gviz/tq?tqx=out:csv` | All 6 sheets reachable with `-L`. Uniform schema: `Serial No, Book Page, Topic, Question, Option A…E, Correct Answer (A–E), Explanation` (11 cols). Valid rows: malwa_vol1 **2039** (1 blank row), vol2 **2842**, horti **1260**, iari **7448** (pages 2→1074, 1060 distinct) ✅ |
| A9 | Telegram field limits vs sheet text | computed max lengths | question max 240 chars (+`"25/50. "` prefix ≤247 < 300 ✅ never truncated). **Options over Telegram's 100-char limit: vol1 18, vol2 12, horti 3, iari 44** → needs a locked rule (L4) |
| A10 | Sheet rotation start | first row of vol1 CSV | vol1 CSV **starts at Serial 21** → a fresh `bidx=0` *is* "vol-1 continues" (serials 1–20 already spent elsewhere). No ambiguity, no back-fill. |
| A11 | Render paid bot | `getMe` on PAID bot (PAID_TOKEN unreadable) | `Quizbotagri2_bot` alive ✅ — **not touched, no redeploy** (paid.db risk) |

---

## B. ⛔ BLOCKER B1 — EXAM BOT IS NOT ADMIN ANYMORE (must be fixed by admin before anything can run)

```
$ curl -s ".../getChatMember?chat_id=-1003784795446&user_id=8585018636"
{"ok":true,"result":{"user":{...,"username":"Arunkatyanquiz_bot"},"status":"member","tag":"Satyam sir"}}

$ curl -s ".../getChat?chat_id=-1003784795446"
permissions: {"can_send_messages": False, "can_send_polls": False, "can_pin_messages": False, ...}
join_to_send: True | has_hidden_members: True | pinned_message: 29092
```

**Meaning:** @agriquizworld is locked to **admins-only posting** (`can_send_messages: False`, `can_send_polls: False`), and `Arunkatyanquiz_bot` is a plain **`member`** → `sendMessage` / `sendPoll` / `pinChatMessage` will all fail with `not enough rights`. The 14-Sep run worked because the bot was admin then; it has since been demoted (or the group default permissions were tightened).

**Fix (admin, in Telegram app, 30 seconds):** Group → Manage → Administrators → Add Admin → `@Arunkatyanquiz_bot` → enable **Post Messages, Pin Messages, Delete Messages** (rest optional). Admins in the group who can do it: Satyam (owner), Mahaveer, Paddy, Shiva, P, Sudha, @agrimanger, Shi, Agrisudha.
Legacy bot `@Malwaquiz_bot` is also `member` — irrelevant (not used for tests, no pin rights needed for legacy LB/alerts; those go by DM only).

I will re-run exactly this check as gate #0 of the verification battery; the live dry-run/test start is gated on the returned `"status":"administrator"`.

---

## C. DATA FACTS THAT NEED AN ADMIN DECISION

**C1 — Today's AFO set (18:00 IST, 15-Sep) is already `picked_at: 2026-09-14 13:26:28`** while still `status: ready` (it was picked for the cancelled 14-Sep test, never marked used):
```
2026-09-13 | ready | set_no 1 | picked_at None
2026-09-14 | ready | set_no 2 | picked_at None
2026-09-15 | ready | set_no 3 | picked_at 2026-09-14 13:26:28   ← already picked
```
Nothing is broken (48 remaining dates 15-Sep→1-Nov all have ready sets, zero uid repeats), but the default must be confirmed: **post set_no 3 today as 15-Sep's set (no re-pick)** — the `picked_at` merely records last pick; the engine will pick-for-date and skip re-pick if `picked_at` is today's date. Alternative: skip AFO today and start 16-Sep with set 4. 13/14-Sep sets stay `ready` **untouched** (not deleted, never retro-fired on a past date).

**C2 — `afo_supply` cannot top up today and needs nothing:** the pool's 2500 uids are all reserved (ledger) and all 48 live dates already have ready sets → **the 05:00 supply job is construction-audit only** (idempotent, verifies coverage + no-repeat, logs+journals, **no Telegram at all**). Building a *new* bank from nemraj/rksharma sheets would be a separate order — not doing it unasked.

**C3 — Old leftovers stay untouched by default** (`kuch delete n ho`): pinned message `29092` (cancelled 14-Sep AFO announce) + its few polls remain. New announces get pinned *in addition*. If you want 29092 unpinned/deleted, say so — one explicit line in the kill/build order.

---

## D. LOCK TERMS (defaults taken from the spec; "LOCK" = admin says go)

**L1 — Clock/day** — Every clock, label, journal day-key, filename = **IST (UTC+5:30)**; `TZ=Asia/Kolkata` in every workflow; engine computes IST from `utcnow()+330min`, never host clock. Journal day key = IST date string. *(SPEC T1)*

**L2 — Slots (locked order, no deviation)** — malwa **11:00**, iari **14:30**, afo **18:00** IST.
- Window: start allowed **go−50min → go+4h**; after go+4h the slot is sealed `missed` forever (no retro-fire). Inside the window but after go = **late start, starts immediately, no countdown**.
- while `now < go`: countdown edits the announce in the last 60s, then polls.

**L2b — iari draw rule (derivation needed, my default):** sheet has 7.03 Q/page avg (7448 Q / 1060 pages), so "5 pages" ≈ 35 Q — that cannot coexist with the locked "20 questions · 30s each" headline. Default: **20 Q/day in strict page order**, journal tracks `bidx = next row index` + `next_page`; a day may end mid-page and the next day continues that page (order never breaks). The announce/result file report the **pages covered that day** (e.g. `Pages 2–9`); a "batch" for bookkeeping = 5 pages consumed. → confirm in Q3 below.

**L3 — Rotation (malwa)** — `bidx` = next unused row of current volume; 20 Q/day; batches of **150 rows** for bookkeeping (`batch = bidx//150`); volume exhausted (`bidx ≥ valid_rows`) → next volume starts **next IST day** (vol1→vol2→horti); all three done → pinned "series complete" congrats + slot closes (step 8 + `closed: series_complete`). Reset rule on rollover: same daily cadence, journal keeps per-volume done markers so a rollover never restarts a volume.

**L4 — Poll text limits (Telegram hard limits: question 300, option 100)** — question max needed = 247 ✅ never cut. Options: truncate to `100` incl. `…` **only if** the cut leaves the option distinguishable; if truncation would make two options in the same question equal, or cut the keyed option ambiguously, that **row is skipped** and the next sheet row is taken (journal advances — never alter the exam semantics). Truncation is logged per test.

**L5 — Live flow (exact UX, per §6)** — 4-line pinned announce (emoji+bold label / date+time / `20 (ya 50) questions · 30s each` / scoring line; AFO line 4 = `+2 right · −0.5 wrong · end me leaderboard + result file 📄`) → countdown (last 60s, edit announce) → per question `sendPoll(type=regular, is_anonymous=False, allows_multiple_answers=False, open_period=30, question="{n}/{N}. {text}")` with HTML-escaped text → drain `getUpdates?offset=…&timeout=1` while open, scoring live → leaderboard ≤48 rows/msg (🥇🥈🥉 then `#n`, `tg://user?id=` links, `%+.1f`) → pinned congrats naming topper → **result file = 6065-format HTML table (scores + answer key), sent as document, UNPINNED**, caption `label + date` → ONE short CTA line → nothing else. Malwa/iari **+1/−0.25**, AFO **+2/−0.5**; unanswered = 0; last answer per user per question wins.

**L6 — Journal + resume** — `state.json` = the only DB (git journal). Keys: `days[IST-date][job]` and top-level `afo18`/`booksend` (compat). Fields: `{step, qidx, sent_i, msg_ann, cd, locked_by, lock_ts, done_at, pages, bidx, volume, missed}`. Steps: **1** announced · **2** polls running (`qidx` every 5 Q, `lock_ts` heartbeat ≤120s) · **3** polls done · **4** LB done · **8** complete. Lock: `locked_by=run-id`, takeover only if heartbeat older than 120s. **Resume never re-announces** and never duplicates: `sent_i` is written *before* `sendPoll`, so a crashed question is skipped on resume (`resume_at = max(qidx, sent_i+1)`). Two-runner push → merge by `max(step,qidx)` + rebase-retry loop on 409.

**L7 — Scheduler (GHA rules)** — every workflow **self-chains by `workflow_dispatch`** (cron = backstop only); new workflows get `push: paths:[<itself>, <engine file>]` self-registration; **never** `cancel-in-progress: true` on test-running workflows; no multi-line inline Python in YAML (files only); `permissions: contents:write, actions:write`; runner GITHUB_TOKEN does all dispatches, PAT only for admin/maintenance API. Workflows: `slot-chain.yml` (dispatcher, cycle cadence 120–180s sleep + rearm jitter 100–190s, timeout 240 min) · `slot-guard.yml` (self-chained ~7 min watchdog, revives a stale chain >25 min + DM admin) · `keepwarm-agent.yml` (Render keepwarm + agent pass + `agents/relay.py` marker dispatch + 150s throttle) · `slot-kill.yml` + `agents/kill.py` (client-side status filter, 15s grace, `git reset --hard origin/main`, seal open jobs `step8+killed`, remove `.KILLTEST`, push, DM admin; runner sets git user.email/name) · `afo-supply.yml` (05:00 IST, audit-only per C2, **never posts TG**) · `booksend.yml` (manual dispatch only, one-off, pins every file, INDEX last with `t.me/c/<chatnum>/<msgid>` jump links + ◀️Prev/📚Index/Next▶️ nav — built but never run without an explicit order).

**L8 — Announce/copy hygiene** — never two copies of the same data on the same day; superseded announce/index/copy that *this* system sent gets deleted **only if** it is a 100% duplicate produced by a crashed retry of the same job/day (journaled message ids only). Old messages from previous runs (e.g. 29092) are never touched unless you order it (C3).

**L9 — Chat routing (locked, no paid-group routing)** — all three tests → **`CHAT_ID = -1003784795446`** (@agriquizworld) via `EXAM_TG_TOKEN` only. `chat_for(job)` returns that constant for all jobs. Admin DMs only for: missed slot, routing fallback, watchdog revive, kill confirmation. Nothing is ever posted to a group without an admin order (booksend = manual dispatch).

**L10 — Text style** — Hinglish, farmer-friendly, short. Labels: `MALWA BOOK VOL 1` (→ VOL 2 / MALWA HORTICULTURE), `IARI BOOK MCQ 2026`, `AFO MAINS TEST (NEW PATTERN)`. Result-file name `MALWA_VOL1_2026-09-15_results.html` style. No keys/tokens/chat-ids in any group text or log.

**L11 — Engine layout (fresh files, rebuilt from scratch; `engine/afo18.py` folded in and then deleted)** —
```
engine/engine.py    config(JOBS)+sheet reader+journal+tg()/tg_file() 429-retry+chat_for()
                    +announce/countdown/polls/LB/file/CTA+subcommands:
                    slotchain | run <job> | prebuild <job> | status | agent | keepwarm | supply | booksend <job> <range> <step>
engine/builder.py   6065-format HTML: render_html(DATA, pages_per, book, author, brand, spb, key, out_path)
engine/afo_mongo.py build | status | pick <date> | mark <date>  (agri.*, idempotent, no TG)
agents/relay.py     .GHA_DISPATCH.json {"items":[{wf,inputs}]} → dispatch → clear → push
agents/kill.py      emergency stop per L7
state.json          {"days":{"YYYY-MM-DD":{job:{...}}}, "afo18":{...}, "booksend":{...}}
```
Legacy `afo18.py` + `afo-today.yml` may be deleted **in the same commit** that lands the rebuild (nothing else deleted). `engine/__pycache__` dropped from the repo (gitignored).

**L12 — Verification gate (nothing enabled before this passes)**
1. `python3 -m py_compile` on every shipped .py (all modes, incl. `agents/`).
2. `yaml.safe_load` on every workflow + `actionlint`-style static checks (no inline python, permissions, timeouts, concurrency).
3. **Fake-clock matrix, 10 cases** with injected `NOW` override, offline Telegram/Mongo/Sheets fakes: idle pre-window · warm window · multi-window overlap · missed-after-4h (sealed, no post) · resume-mid-polls (no prebuild + no re-announce) · step≥8 skip · afo closed after 2026-11-01 · one job's error isolated (others still run) · exact 14:30:00 IST boundary · afo next-day advance.
4. **Live dry-run** at a harmless hour: one slot-chain cycle → journal untouched, rearm dispatched, admin got no false alarm.
5. Re-check B1 (`getChatMember` → `administrator`) then PAT `PUT /actions/workflows/{id}/enable` and seed the day.

---

## E. TODAY'S PLAN ONCE LOCKED (15-Sep, IST)

| Slot | Behaviour right now (11:56 IST) |
|---|---|
| 11:00 malwa | window still open (till 15:00). If you approve, chain starts within ~1 min of enable → vol1 from Serial 21 (bidx 0) = 20 Q, late start, no countdown. Otherwise sealed missed and starts tomorrow 11:00. |
| 14:30 iari | on time (countdown), 20 Q strict page order from page 2. |
| 18:00 afo | on time, set_no 3 (C1), 50 Q, +2/−0.5. |

## F. BUILD ORDER AFTER LOCK (stages, each with its own committed verification output)
1. `engine/engine.py` core: config/journal/tg/sheets/mongo reader + `status`. → compile + unit prints.
2. Exam flow (§6 UX) for all 3 jobs + `builder.py` result files. → compile + offline rehearsal (fake TG) of a 3-Q mini test.
3. Scheduler: `slot-chain.yml`, `slot-guard.yml` (+ self-registration push triggers). → YAML safe_load + fake-clock matrix (10 cases).
4. `keepwarm-agent.yml` + `agents/relay.py` + `slot-kill.yml` + `agents/kill.py` + `afo-supply.yml` (+ `booksend.yml`, dispatch-only). → compile + YAML + kill self-test.
5. Self-review pass (adversarial bug hunt) + fix + re-run whole battery.
6. Enable workflows (PAT), gate #0 on bot-admin re-check, then live proof per slot.

**Report format promise:** every stage ends with the exact command + its output. No "done" without it.


---

## G. FINAL LOCKED DECISIONS (admin answers, 2026-09-15) — these override the defaults above
- **L1–L12 approved as written.** Build proceeded on them.
- **iari draw rule = option (b):** all questions of the next 5 book pages (N = actual count, announced as-is). No 4-per-page trimming.
- **AFO 15-Sep** = post the existing set_no 3 (no re-pick; `pick()` is idempotent and only re-stamps `picked_at`/`status`).
- **Malwa 15-Sep = sealed** by explicit admin order (`step 8, missed, sealed_by: admin_order`); VOL 1 continues 16-Sep 11:00 from serial 21.
- **Bot admin rights:** admin will add @Arunkatyanquiz_bot as admin after the build; engine blocks any announce until the live gate (#0) reports `administrator`.

## H. VERIFICATION GATE RESULT (2026-09-15)
- `python3 tests/verify_all.py` → **GATE RESULT: GREEN** (py_compile 8/8 · yaml 6/6 · sheet-key resolution · offline smoke · battery 12/12)
- Live dry-run (GHA run 34938577019): idle cycle, journal semantics unchanged, **0 group posts, 0 admin DMs**, rearm decision logged, self-dispatch + watchdog verified.
- Real-source rehearsal (no posts): iari 15-Sep n=56 (pages 2,4,5,7,8), malwa 16-Sep 20 Q from serial 21, AFO bank 50/50 ready with 0 hard audit problems.
