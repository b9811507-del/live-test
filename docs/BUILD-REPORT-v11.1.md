# v11.1 AMENDMENTS (admin order, 2026-09-15) — what changed and the evidence

Four orders were implemented on top of the locked v11 build. Nothing else in L1–L12 was touched.

| # | Admin order | Implemented as | Verified by |
|---|---|---|---|
| 1 | Language: Hinglish → English | `engine/translator.py` — every user-facing string is authored professional English (`T` table). Group, DM, result-file and admin-alert text all switched. | battery case 2 asserts `hinglish=0` over every group message |
| 2 | "translator add karo jo professional translate kare" | `translator.translate()` — provider chain Google clients5 → gtx → MyMemory, bounded cache, agricultural glossary/register polish, offline fallback. Used for sheet **topics** (and any Hindi/Hinglish dynamic text). CLI: `python3 engine/engine.py translate "<text>"`. | live: `मृदा उर्वरता और फसल चक्र से उत्पादन बढ़ता है` → `Soil fertility and crop rotation increase production`; `पशुधन विकास में संतुलित आहार का महत्व क्या है` → `What is the importance of balanced diet in livestock development?` |
| 3 | After the announce, only a **15-second** countdown | `COUNTDOWN_SECS=15` (env-tunable). Announce is pinned 2 min before the start time, the pinned message is edited at 15/10/5/4/3/2/1 → "Starting now — good luck!", then poll #1. The old 60-second pre-start edits are gone. Runs arriving more than `DEFER_SECS=240` early now only re-arm (runner-minute saver). | battery case 2: `countdown_ticks=[15,10,5,4,3,2,1,0]`; case 9 (exact 14:30 boundary): `max countdown tick = 15` |
| 4 | LAST message after every test = paid batches, click → all batches with payment links, payment → one-time join link in the student's chat box | `engine/paid.py`: showcase message with one button per batch (payment link embedded, or a deep link into the bot DM), `/start buy_<batch>` flow, "I have paid" claim, Telegram-native invoice path, `createChatInviteLink(member_limit=1)` → link delivered by DM, `/mybatches`, admin commands, auto-approve of join requests for enrolled students, `/admin` pending-approve-revoke-stats. | battery 13: `invite_links=1 member_limit=1 link_sent=True entitlement=issued`; case 14 (invoice → auto link): `invoices=1 invite_links=1`; case 15: desk stays silent during a live test (`getUpdates calls=0`) |

## Message order in the group (per test)
1. announce (pinned, 2 min before) → 2. 15-second countdown (same message edited) → 3. N polls (30s each) →
4. leaderboard (48 rows/msg) → 5. congratulations (pinned) → 6. result file (document, **not** pinned) →
7. one-line daily schedule → **8. PAID BATCHES message (last, with payment buttons)**.

## Enrolment flow (student side)
group button → bot DM (`/start buy_afo`) → batch detail + **Pay securely** button →
payment → **I have paid** (or Telegram invoice `successful_payment`) → bot creates a **single-use**
invite link (`member_limit=1`, 24h) → link arrives in that student's chat box, and the admin gets an
enrolment DM. If the bot is not yet admin-with-invite-rights in that batch group, the student is told
the link is coming and the admin gets the exact fix; links are auto-issued on the next pass.

## Inputs still needed from the admin (only these block full automation)
1. **Payment links** for the three batches → secrets `PAID_LINK_AFO`, `PAID_LINK_PASHU`, `PAID_LINK_CANE`
   (until then the buttons open the bot DM and the student is told the link comes from the batch team).
2. **AFO Mains batch price** → secret `PAID_PRICE_AFO` (the other two are ₹151 each, already set).
3. **PASHUDHAN chat id is invalid**: the spec value `-10033947957354` returns `Bad Request: chat not found`
   (supergroup ids are `-100` + 10 digits). Send the correct id → secret `PAID_CHAT_PASHU`.
   AFO `-1003687531473` and Sugarcane `-1003707610763` are verified: the bot is **administrator with Invite Users** there.
4. Optional but recommended for *instant* payment verification: a Telegram Payments provider token
   (BotFather → Payments) → secret `PAY_PROVIDER_TOKEN`. Without it, the link is issued on the
   student's "I have paid" tap (mode `auto`, admin alerted) or on admin approval (`PAID_VERIFY=approve`).

## Still open from v11
* **@Arunkatyanquiz_bot is not admin in @agriquizworld** (live check: `status=member`, group is
  admins-only) → no test can post until that is fixed.
* Render paid-bot service is suspended by its owner (not redeployed).
