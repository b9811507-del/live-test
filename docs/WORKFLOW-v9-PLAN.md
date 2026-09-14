# v9 PLAN — neat & clean workflow (approved fixes; NO code touched until user says "GO")
Date: 2026-09-12. Slots currently PAUSED (disabled_manually) so no wrong-time fire can hit the group.

## User's directives (this turn) — all covered below
| # | Directive | v9 design |
|---|---|---|
| 1 | Timezone = Indian; 11:00 AM Malwa · 2:30 PM IARI · 6:00 PM AFO full-length | Crons stay UTC-mapped (05:15/29/50, 08:45/59/15, 11:35/29/10) BUT run-step gets a **hard IST window guard**: engine refuses to post unless `now(IST)` ∈ [slot_start−3min, slot_start+25min]. Missed/queued GitHub fires → **auto-SKIP** (never back-to-back again). All messages/log/`TZ: Asia/Kolkata` env + `date` in announce uses IST explicitly. |
| 2 | AFO full-length must show `📊 3/50` (position), NOT raw sheet serial | Poll question header: `📊 <i>/<n> · <Q text>`; file (6065) same counter; sheet serial retained only inside answer-key meta for revision lookup. Books (Malwa/IARI) keep today's `Q1..Qn` (per-day numbering) — n = 9..18. |
| 3 | "Payment section me key setup bol raha hai" | Keys VERIFIED OK right now: live ₹1 order created + auto-cancelled (`order_TazxcrTz9FcW1n`). The misleading "Payment setup pending (keys)" alert fires only when order-creation call transiently fails. Fix: retry ×2 (2s), on final failure → buyer ko "⏳ Link ban raha hai, 1 min me bhejenge" + **admin ko error DM** + background auto-retry job; never show "keys" wording to students. |
| 4 | Group me PIN sirf START message (announcement) | Engine: pin announce ONLY. Leaderboard/congrats/file/tomorrow = NO pin. Yesterday's announce auto-unpin when today's pins (1 pin total, always). Existing stale pins → cleanup list below (needs user OK). |
| 5 | Agents ne galat-chalne wale test ko roka/kya nahi? | Root-caused: agent-doctor date-filter param tha `created=..X` (= "before X") then filter "after" → 0 matches → "actions: 0" while slot-afo failed twice. v9: proper `created:>X` + new checks: (a) OFF-WINDOW fire = CRITICAL DM, (b) run failed but no rerun possible → LLM analysis DM same pass, (c) sentinel: slot fired outside window → auto-disable workflow + DM (hard safety). |
| 6 | AFO IndexError crash (aaj raat fail hua) | Engine `afo_pool` skip guard exists but state prebuild ne empty/short list di → run pe IndexError. v9: prebuild writes ONLY if 50 Q selected else keeps yesterday & marks "PREBUILD FAIL" DM; run asserts `len(qs)==n` before first send — else abort silently (no partial spam ever). |

## Exact daily timeline after GO (all IST)
- 10:45 prebuild Malwa → 11:00 announce+pin → countdown → 9–18 polls 30s → leaderboard → congrats → file → CTA → tomorrow (NO pins after announce) → 11:2x state commit
- 2:15 prebuild IARI → 2:30 full flow same shape
- 5:05 prebuild AFO (50Q, 📊 1/50 counters) → 6:00 flow (25 min quiz) → ends by 6:45
- Agents: doctor */30, sentinel */15 — DM sirf problem/hint pe, group ko kabhi touch nahi
- Failure in any slot → NO retry-at-random-time: skip + DM; kal schedule normal continue

## Group cleanup (needs explicit OK — pending)
1. Unpin everything except today's/yesterday's announce (jo bhi leaderboard/file/tomorrow pinned pade hain)
2. Delete off-schedule garbage posts window 22:10–00:15 UTC runs ne jo group me daale (engine message-id log se list bana ke list du pehle, phir delete)
3. Ek fixed "📌 Rules & Timings" pin? (optional, user decides)

## Rehearsal before GO-live (recommended)
Private demo group (already exists from demo day): fire full Malwa+AFO once with v9 code → user confirms counters/pins/timing → phir crons ENABLE (re-enable 2 API calls) + next 11:00 = live Day-1.

## After approval, code deltas (small, surgical)
engine/engine.py: IST window guard fn; AFO [i/n] label in send_poll + builder; prebuild sanity assert; pin policy → only announce (delete rotation block).
renderapp/paidbot.py: make_order retry + friendly pending text + admin error DM.
agents/doctor.py: created:>+ window fix, off-window detection. agents/sentinel.py: slot-fired-outside-window → disable+DM.
Workflows: TZ env + keep `on: schedule` same.
Then: commit → rehearse → enable.
