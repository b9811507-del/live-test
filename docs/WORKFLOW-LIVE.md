# LIVE TEST SYSTEM — FINAL v5 (POLL format per user screenshots) (rules locked; build on user "OK")

Group for ALL THREE slots: **AGRI QUIZ WORLD (@agriquizworld)**. Bot: @Malwaquiz_bot (admin+pin+delete verified ✅).
Infra: GitHub `live-test` (engine + state.json in git = pointers/ledger) · GHA crons · Render `livescore` (test page, /score, /board). Keys verified.

## Timing & marking (v4 — USER RULES)
- **⏱ EVERY slot: 30 Sec/Question ONLY** → duration = Q × 30s. AFO 50Q = **25 min**. Book 12Q = 6 min, 15Q = 7.5 min. Auto-submit at end; first attempt only.
- **📚 BOOK tests (Malwa Vol1/Vol2/Horti + IARI): +1 right · −0.25 wrong** → final = R − 0.25W.
- **🎯 LIVE test (AFO MAINS): +2 right · −0.5 wrong** → final = 2R − 0.5W.
- Leaderboard rank: final ↓ · ✅ ↓ · ❌ ↑ · name A→Z.

## Slots
| Time IST | Source | Selection | End condition |
|---|---|---|---|
| 11:00 AM | MALWA | STRICT sequence 3 pages/day: Vol1 p1→466 → Vol2 p1→406 → Horti p1→180 | till all books finish (no date) |
| 2:30 PM | IARI BOOK MCQ 2026 | 3 pages/day p1→1074 | till book finishes (no date) |
| 6:00 PM | AFO 25-subject pool (~20,850Q, model papers out) | 50Q seeded-random no-repeat | **only till 2026-11-01**, then 🏁 closing msg + overall series board; auto-off |

## Exact group flow — EVERY slot identical shape (demo: iari/leaderboard-demo.html)
1 announcement (pinned; title/sheet-name → By SatyamSir → date+Pages/Q line → "⚡ N Q · 30 Sec/Question · ✅ +X · ❌ −Y"; AFO adds 1-Nov CTA line + /join code) + [🚀 START TEST → Render page, locked till GO]
2 countdown one message edited 1️⃣5️⃣→…→🚀 (≈3.5s steps)
3 test window (30s/Q) → auto-submit (offline queue + retry)
4 🏆 leaderboard — EVERY submitter; >~45 rows auto-split "2/5, 3/5…" (no cutoff); medals top3
5 🎉 CONGRATULATIONS TO OUR TOP 3 RANKERS + Keep up the great work
6 📄 test HTML file (offline re-attempt)
7 💪 Great Effort + **JOIN NOW CTA — on BOOK slots too** (generic paid-batch wording; AFO adds "Last date 1 Nov") → paid bot flow (catalog→Razorpay→webhook addChatMember+PDFs; "opening soon" until keys)
8 🔜 tomorrow (tomorrow's date + pages/Q of all 3 slots)
Pin rotation: leaderboard/congrats/file/tomorrow pinned; yesterday's unpinned (1 unpin/day).
AFO day end = 🏁 series-complete message (after 1-Nov test).

## Cron (UTC)
05:25 build+warm → 05:30 Malwa · 08:55/09:00 IARI · 12:25/12:30 AFO · keep-alive 10-min · date-gate hourly for AFO end. State committed after each slot; failure → digest DM to SatyamSir + auto-retry next morning.

## Pending until OK
1. Razorpay keys + batch list (placeholder until then — non-blocking).
2. Verified-name mode yes/no (default ON).
3. First live day (or rehearsal-with-REHEARSAL-tag first).

## v7 — PAID BOT (JOIN NOW flow) — @Quizbotagri2_bot (8533597307)
CTA button → t.me/Quizbotagri2_bot?start=batch → catalog: 7 batches — AFO Mains ₹199 · Nemraj ₹99 · IARI ₹99 · Malwa(V1+V2+Horti) ₹151 · RK ₹99 · Sugarcane ₹151 · Pashudhan ₹151 — har card: price, **Validity: Lifetime, Attempts: Unlimited**, "👉 Pay ₹X & Join" → Razorpay ORDERS API + hosted checkout page /p/<note>/<tok> (Payment Links API 404 on this account — DO NOT retry) → HMAC /confirm + webhook + poll_pending backstop → **one-time join link DM** (member_limit=1 via MT bridge `MT_URL/genlink` when session available; else admin-fallback "show txn to admin"). /status = order history.
Bot groups: AFO Selection Batch 2026 (-1003687531473) = ADMIN ✓. Pending add+admin: Malwa -1003761821341, RK -1003880198347, IARI -1003922097468, Sugarcane -1003707610763, Pashudhan -10033947957354, Nemraj (id? link do).

### v7.2 DEPLOY STATUS (2026-09-11) — ALL LIVE
- GitHub: repo b9811507-del/live-test (public, main @ 748cda0). Secrets: TG_TOKEN, CHAT_ID, RENDER_URL, RENDER_SVC, ADMIN_KEY. 4 workflows+crons ACTIVE → **first real AFO test tonight 18:00 IST** (crons UTC 11:35 prebuild / 12:29 run = 18:00 IST / 13:10 wrap).
- Render: **livescore** srv-daht4gh594qs738g90cg → https://livescore-zp5w.onrender.com LIVE, healthz ok, paid-bot poller thread running (getWebhookInfo: empty url, allowed msg+callback). Paid flow routes ready: /p, /confirm, /rzp/webhook, /soon.
- Render gotchas (fixed): rootDir ignored via API → build `pip install -r renderapp/requirements.txt` + start `cd renderapp && gunicorn app:app ...`; **app.py needs `app = APP` alias**; env update = `PUT /services/{id}/env-vars` with RAW ARRAY body only.
- Still OPEN: (1) user must re-paste **session API** (api_id/api_hash/session_string) → bot ko 5 groups me add+admin + one-time invite links (Bot API se impossible); (2) **Nemraj group link/id**.

### v8 — ADMIN AI CONTROL + GUARDIAN AGENTS (2026-09-11 late)
Paid bot v8: only **ADMIN_ID 1138783169** gets AI chat + 🛠 panel (➕ Add Batch / 💰 Change Fees / 🗑 Remove / 📊 Today / 🔄 Pull / 📦 Push); public users = buttons-only, free text NEVER answered (silently forwarded to admin DM, payment words get 🔔). Natural language → LLM JSON action: "AFO fees 50 badha do" → +50 calc → set_price; regex fallback if LLM dead. Chain: Groq gpt-oss-120b → OpenRouter llama-3.3-70b → Mistral small → Gemini-3.6-flash ×2 (llmsupport.py; **UA header required** else Cloudflare 403 on urllib).
Batches live in sqlite + pushed to `state/batches.json` on GitHub (source of truth at boot; NO push when unchanged — old code looped deploys, fixed v8.1). Render autoDeploy now OFF (`autoDeployTrigger:"off"`) — restarts only manual/sentinel.
Agents: **agent-doctor** (*/30: failed runs → transient? rerun : LLM patch engine/renderapp .py, py_compile guard, push+rerun, DM admin) + **agent-sentinel** (*/15: healthz ×3 → redeploy, stray webhook delete, pending>15 restart, slot-check ONLY in slot window & only if slot workflow ran ≤16h; DM only on trouble). Both verified success runs 11:22 UTC. GH secrets now 13 (LLM keys, ADMIN_CHAT=1138783169, PAID_BOT_TOKEN, RENDER_API_KEY...).

### v8.2 — SESSION STRING verdict + JOIN-REQUEST GATE (11 Sep 11:45 UTC)
User's session string = encrypted generator format ([4B head][256B key][4B api_id≈149,974,236]) — NOT Telethon/Pyrogram raw; key slices × dc1-5 = 45 combos all `AuthKeyUnregistered` → unusable (no auto group-add from our side).
PIVOT (no session needed): **join-request auto-gate** — paid buyer pays → taps group join link (request mode ON) → `chat_join_request` update → paid order match? → `approveChatJoinRequest` instantly (order → delivered). Unpaid → DM to admin with ✅ Approve / 🚫 Deny buttons. Stronger than one-time link (link leak = still gated). getUpdates allowed += chat_join_request ✓ LIVE (8f4e735, webhookinfo verified).
Nemraj group: chat id `-1003853396327` (from webK #-3853396327) — in state/batches.json ✓.
USER TODO: (1) add @Quizbotagri2_bot as **admin** in 6 groups (all except AFO where already admin) — approveChatJoinRequest needs it; (2) each group's invite link → set **Request Admin Approval ON**, send links here → stored as JOIN_<batch> envs (else buyer DM shows generic 'request to join'); (3) optionally send my.telegram.org api_id+api_hash if real string needed later.

### v8.3 — "bot no response" INCIDENT POSTMORTEM (11 Sep 12:3x UTC)
Root causes: (1) orphan sandbox demo `python3 app.py` (pid since 10:24) stole all getUpdates — killed; (2) paidbot eager-import restructure (llmsupport → renderapp/llmsupport.py, app.py top-level import) — fixes partial-init deadlock; (3) paidbot now forces IPv4 via socket.getaddrinfo patch (Render↔TG IPv6 blackhole insurance). Diagnostics added permanently (admin-key gated): /admin/nettest (DNS+TG/gen/rzp timing), /admin/ping (DM self-test), /admin/selftest (handle() smoke ×3). All green: nettest tg=0.6s, ping msgs 17-18 delivered, selftest no-exception ×3, allowed=[msg,cb,join_req] pending=0. Commits: 4237533→0d8054f→14aa9cb (final = v8.3.1+diag). NOTE: never run bot poller in sandbox with real token again (409/update-steal hazard).

- MongoDB Atlas (AFO set factory, LIVE): mongodb+srv://mailforfulltest_db_user:1vmiEQA28y0ok4Fh@cluster0.k85vzmp.mongodb.net — db agri; 50 sets prebuilt 13-Sep→1-Nov, audit clean (old flipkartagent cluster abandoned — allowlist blocked).

- **v9-payment-fix (LIVE @ f47beb6):** Razorpay order-create retries(2, backoff 2s/5s) on 429/5xx/network, fail-fast 4xx; stale (>13min) 'created' orders expired & replaced (double-charge guard); failure → row marked failed + throttled 🚨 DM to admin; student text never mentions keys/setup ("server busy — 2 min me try karein"); checkout page auto-recovers via /pstatus poll (webhook late = paid status shows anyway); modal-close & payment.failed handled politely. Selftest now live-tests ₹1 order on Render (last: order_Tb17WbZEEge8Pt ok).

- **paidbot bot-no-response ROOT CAUSE (fixed @ 8f6b29f, LIVE):** (1) gunicorn master imported app → started poller thread in MASTER → forked workers → thread died in worker (threads don't survive fork) → nobody polled; module-level start was removed, workers self-start poller via _ensure_bot before_request hook (keepwarm /healthz ping activates it after each deploy). (2) Render runtime has NO curl binary — all transport is urllib again. (3) TG calls pinned to api.telegram.org's static IP (149.154.166.110) + Host header, zero getaddrinfo in loop (unboundedable DNS hang had frozen it before; hourly opportunistic refresh via poll_pending). (4) lazy in-function imports removed (fork-inherited import-lock deadlock). (5) All slow work (GH push/pull, rzp poll) runs in a queue drained by the loop between longpolls — no per-call threads (container starved Thread.start). (6) Payment: order lazily created by checkout page via /startpay (gunicorn thread) — bot tap replies in 0.3 ms, never blocks. (7) keepwarm cron */5 hits /healthz + /admin/loopfix (breaker: if loop stuck >150s, worker self-kills; respawn wakes on next ping). Verified LIVE: loop cycles 28s with age 0-23s, no 409s, getMe 0.5s.

- **razorpay 400 root cause (FIXED @ 3e93cea LIVE, 2026-09-12):** order-create body carried `partial_enabled:false`; Razorpay removed the partial-payments feature and now 400s extra fields (`extra_field_sent`). Students' taps → order create fail → "PAYMENT ISSUE: order create fail note=...". Fix: field removed; api_post now embeds Razorpay's real error description in the admin alert. Verified: same-shape order create OK (order_Tb415vuwhszVgz sandbox, order_Tb4Bwxnftgp2jD on Render). Failed order rows stay 'failed'; re-tap Pay → fresh order (make_order_local only reuses 'created').

## 2026-09-12 — paid ✅ but no join link (nemraj ₹99 IARI) — ROOT CAUSE + FIX
- Razorpay: `pay_Tb7JsYprmXgYWM` captured, notes.ref=`8822719176:iari:1789214201`; webhook order.paid delivered → fulfill() ran → order marked paid (live pstatus showed paid before redeploy).
- BUT no one-time link: `gen_onetime_link()` was MT-bridge-only; MT_URL unset on Render → returned None → fallback "send join request" DM; admin got "/give" alert.
- Neither @Quizbotagri2_bot nor @Malwaquiz_bot is a member of paid group IARI (-1003922097468) (verified via API: "chat not found").
- FIX `f6ab3f6` (live): gen_onetime_link now also tries Bot API createChatInviteLink(member_limit=1) via paid bot + admin alert on failure.
- REQUIRED USER ACTION: add @Quizbotagri2_bot as ADMIN (Invite Links right) in every paid batch group:
  IARI -1003922097468, malwa -1003761821341, afo -1003687531473, rk -1003880198347, sugarcane -1003707610763, pashudhan -10033947957354.
- nemraj recovery: after adding bot → DM @Quizbotagri2_bot: `/give 8822719176:iari:1789214201` (re-inserts row + generates link + DMs student).
- KNOWN GAP (queued, not approved): orders/fulfil state in ephemeral SQLite — any redeploy wipes pending orders. Candidate: move orders to Atlas Mongo. Also nemraj's paid-row vanished after redeploy (recover via /give as above).

## 2026-09-12 eve — /give saga closed
- 18:16 alert "400: chat not found" = bot tab tak group me nahi tha; user ne 18:17 add kiya. 18:17 re-run /give → UNIQUE(uid,batch,status) dup-row crash (17:52+18:16 runs ke leftovers) → fulfill abort before link-gen.
- FIX live `d694a65`: fulfill uses UPDATE OR IGNORE + deletes non-paid dup rows per note; /give inserts only when note absent → repeated /give now idempotent & safe (offline e2e: dup scenario passes, paid count stays 1).
- Manual delivery: one-time link https://t.me/+Mjv_f_1xzGkyYmY1 (IARI, member_limit=1, name=pay:8822719176:iari:1789214201) DM'd to nemraj via paid bot (msg id 69) — sandbox GET API path.
- Bot admin+can_invite verified in: IARI, malwa, afo, rk, sugarcane. **PENDING: pashudhan -10033947957354 (chat not found)** — user must add @Quizbotagri2_bot there.
- .git/config excluded from snapshots → git identity+remote must be re-set EVERY turn before commit/push (use git remote ADD, set-url fails when origin missing).

## 2026-09-12 19:0x — paid-groups visibility audit (per user order)
- All 5 groups w/ bot: has_visible_history=True → new joiners see full history. Content exists (IARI next-id 453, malwa 6104, afo 12365, rk 7640, sugarcane 7043).
- Nemraj: verified `member` of IARI. Blank view was pre-welcome/sync — no setting issue found.
- Posted+pinned professional welcome (paid perks, slot timings, poll-only rules) via paid bot as admin: IARI#453, malwa#6104, afo#12365, rk#7640, sugarcane#7043. ADDITIVE ONLY — nothing deleted/moved.
- Pashudhan -10033947957354: paid bot still NOT a member (API can't self-add; session string = generator-encrypted, unusable since v8.2) → USER action: add @Quizbotagri2_bot as admin (Invite+Pin rights).
- Bot rights verified in 5 groups: admin w/ can_invite + can_pin + can_change_info.

## 2026-09-14 — slots dead since Sep 11 + per-batch routing for IARI
- ROOT "test time pe nahi hua": slot-malwa/iari/afo workflows disabled_manually (freeze pending user). RE-ENABLED via API 09:41 IST — today 11:00/14:30/18:00 IST crons live again.
- User added @Quizbotagri2_bot as admin — WRONG bot for quiz posting; quiz engine uses @Malwaquiz_bot (TG_TOKEN default). Not yet in IARI ("chat not found").
- Engine routing `2277d56`: chat_for(job) — env {JOB}_CHAT → membership probe (getChatMember admin/creator/member) → route to paid group; else fallback @agriquizworld + admin alert. Secret IARI_CHAT=-1003922097468 set. Offline 3-path test ✓.
- IARI hidden-content: has_visible_history=True now; join-era snapshot explains blank view for old joiners. Resent pinned cards: welcome #453 + test card #457 (engine 4-line format). Bots post fine as admin (send/pin/instant-polls); message READ never needed.
- USER TODO: add @Malwaquiz_bot admin (Send+Pin) in IARI group before ~14:20 for today's routing; pashudhan still needs @Quizbotagri2_bot.

## 2026-09-14 — IARI content relay (per resend order)
- Own-card dedance done: #457 deleted+unpinned, #453 already gone (user had deleted), combined engine-format card #459 posted+PINNED. Zero dup.
- Bot-API fact: no bot can READ group history (admin or not) → human old posts unrecoverable by us; session string remains unusable (v8.2).
- Built RELAY `ba0ebe6` (live): admin DM containing forwarded msg → exact re-post into IARI paid group (photos/docs/videos via file_id) + auto-pin. Dedupe via _RLY_SEEN (sha256 kind|date|text|filefront). Flood-safe: non-dict tg result → requeue front, break; batch cap 6/drain + _bg self-rearm → loop never starved. /relay = status.
- USER FLOW: select-all old messages → forward to @Quizbotagri2_bot → bot re-posts+pins (~25/min) → admin gets ♻️ counts → then user deletes old block in group.
- Offline tests: capture/dedupe/non-forward-ignore/cap/flood-requeue/retry → all ✓. Loopinfo post-deploy clean.
