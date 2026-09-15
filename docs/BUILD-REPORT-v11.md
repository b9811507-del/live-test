# AGRI QUIZ DAILY EXAM SYSTEM v11 — BUILD REPORT
_Everything below is verified with the command/evidence shown. Nothing claimed that isn't in the output. Tokens never printed._

**Status:** built fresh, pushed to `b9811507-del/live-test@main`, LIVE dry-run passed, chain running.
**One action needed from you:** make `@Arunkatyanquiz_bot` **admin** in @agriquizworld (see §2) — aaj ka IARI + AFO isi par blocked hai.

---

## 1. WHAT LANDED (fresh files, main = 75858279 → now)

```
engine/engine.py     config(JOBS)+IST clock+sheet reader+journal(git)+tg()/tg_file() 429-backoff
                     +announce/countdown/polls/leaderboard/file/CTA + slotchain|rearm|run|prebuild|
                     status|ready|guard|agent|keepwarm|supply|booksend|dispatch
engine/builder.py    6065-style self-contained HTML (scores + answer key + question-wise)
engine/afo_mongo.py  build|status|audit|pick|mark|supply  (agri.afo_sets / afo_used_q / afo_supply)
agents/relay.py      .GHA_DISPATCH.json -> dispatch -> clear marker (push)
agents/kill.py       emergency stop: cancel slot-chain/guard (client-side status filter) -> 15s grace
                     -> git reset --hard origin/main -> seal open jobs step8+killed -> push -> DM admin
.github/workflows/   slot-chain · slot-guard · keepwarm-agent · slot-kill · afo-supply · booksend
state.json           journal (13-Sep + 14-Sep history kept; 15-Sep malwa sealed by your order)
tests/               fake_clock.py (12-case battery) · verify_all.py (the gate) · fixtures
```
`engine/afo18.py` was **folded into engine.py** (your "keep or fold" option) and `afo-today.yml` (disabled) was removed in the same commit. Nothing else was deleted: no group message, no file, no Mongo doc. `state.json` keeps every historical entry.

## 2. ⛔ ONE BLOCKER — 30 seconds of your time

```
$ curl ".../getChatMember?chat_id=-1003784795446&user_id=8585018636"
{"status":"member","tag":"Satyam sir"}
$ curl ".../getChat?chat_id=-1003784795446"
permissions: {"can_send_messages": false, "can_send_polls": false, "can_pin_messages": false}
```
@agriquizworld is **admins-only posting** and `@Arunkatyanquiz_bot` is a plain **member** → sendMessage/sendPoll/pin would fail.
**Karo:** Group → Manage → Administrators → Add Admin → `@Arunkatyanquiz_bot` → tick **Post Messages + Pin Messages + Delete Messages**.
Engine ka behaviour: rights check har cycle me; jab tak admin nahi, **kuch bhi group me post nahi hoga** (verified in battery case 11: `group_msgs=0`, journal `blocked`, ek admin DM). Jaise hi admin banega, agla cycle slot ko late-start kar dega (window me rehte hue).

## 3. TODAY (15-Sep IST) — what the live chain will do

| Slot | State | Detail |
|---|---|---|
| 11:00 malwa | **sealed** per your order | journal `step 8, missed, sealed_by: admin_order`; 16-Sep 11:00 se VOL 1 continues (serial 21 = `bidx 0`) |
| 14:30 iari | scheduled, **needs the admin rights** | window 13:40 → announce + countdown → polls 14:30. Today's frozen paper: **n=56, pages 2,4,5,7,8** (real sheet, 0 skips, 0 truncation) |
| 18:00 afo | scheduled, **needs the admin rights** | window 17:10 → announce → 50Q set_no 3 (today's, no re-pick), +2/−0.5, ends ~18:27 then set marked `used` |

Slots jo miss ho jayein: go+4h ke baad engine unhe `missed` seal kar deta hai aur **retro-fire kabhi nahi karta**. Aaj IARI 18:30 tak, AFO 22:00 tak ka window hai — rights jaldi do to dono chal jayenge (late start).

## 4. VERIFICATION EVIDENCE (exact output)

**Gate (compile + YAML + sheets + battery) — `python3 tests/verify_all.py`:**
```
== 1. py_compile ==        ok agents/kill.py · agents/relay.py · engine/afo_mongo.py · engine/builder.py
                           ok engine/engine.py · tests/fake_clock.py · tests/make_fixtures.py · tests/verify_all.py
== 2. workflows ==         ok afo-supply.yml · booksend.yml · keepwarm-agent.yml · slot-chain.yml · slot-guard.yml · slot-kill.yml
== 3. offline smoke ==     status rc=0 | GATE0 chat=-1003784795446 bot=@Arunkatyanquiz_bot can_post=True can_pin=True reason=admin
                           ok sheet keys resolve -> iari=1sUgWsko|malwa_vol1=128DIQLj|malwa_vol2=1UgnIe-g|malwa_horti=1YcJWVgW
== 4. fake-clock battery == battery: 12/12 cases passed
==== GATE RESULT: GREEN ====
```
The 12 cases (fake clock, offline Telegram/Mongo/Sheets, every "send" recorded and asserted):
```
1  idle pre-window                         PASS  group posts=0 polls=0 steps=[0,0,0]
2  warm window (announce+countdown+20Q)    PASS  announce=1 polls=20 open30=True edits=1 pins=2 lb=1 docs=1 cta=1 step=8
3  multi-window overlap                    PASS  announces=2 polls=35 (20 malwa + 15 iari) both step=8
4  missed after go+4h                      PASS  sealed=[True,True,True] group_msgs=0 admin_dms=3
5  resume mid-polls                        PASS  re-announce=0 polls=10 first_q='11/20.' plan_rebuilt=False
6  step>=8 skip                            PASS  group posts=0 polls=0
7  afo closed after last_day               PASS  closed=schedule_end, silent
8  error in one job isolated               PASS  malwa.last_error=True, iari still step=8, rc=0
9  slot_go exact 14:30:00 boundary         PASS  polls=35 countdown_edits=0
10 afo next-day advance                    PASS  set_no=4, 50 polls, trunc=1, max_opt_len=100, 15-Sep stays ready
11 SAFETY bot not admin                    PASS  group_msgs=0 blocked=True admin_dms=2
12 SAFETY booksend smoke                   PASS  files=2 pins=3 index=1 nav_edits=2
```
**Live dry-run on real GHA** (one idle cycle at 12:18 IST, run 34938577019):
```
[12:18:13] cycle malwa 2026-09-15: phase=done step=8
[12:18:13] cycle iari 2026-09-15: phase=idle step=0
[12:18:13] cycle afo 2026-09-15: phase=idle step=0
[12:18:13] cycle done: {'malwa': 'done', 'iari': 'wait', 'afo': 'wait'}
[12:20:54] rearm: no further cycle needed today (done/sealed/closed)
```
Journal untouched in meaning (`days: {…'2026-09-15': {afo:0, iari:0, malwa:8}}`, `msg_ann today: all None`), **zero group posts**, admin DMs = 0 (`dm keys: []`) → **no false alarms**.
Self-chaining proven on the runner: `dispatch: slot-guard.yml dispatched` / `dispatch: keepwarm-agent.yml dispatched`, `guard: chain alive (in_progress)`. `slot-kill`/`booksend`/`afo-supply` push-runs are **skipped** by `if:` guards (never fire from a push).

## 5. DESIGN DECISIONS TAKEN (all inside your locked terms)

1. **iari = whole 5 pages/day** (your pick b): N is whatever those pages hold — today 56 Q at 30s ≈ 28 min. Average ≈ 35–60 Q/day depending on page density.
2. **Journal steps** 1 announced / 2 polls (`qidx` every 5Q + `lock_ts` heartbeat ≤120s) / 3 polls done / 4 leaderboard / 8 complete, **plus a per-question `sent_i` claim written *before* `sendPoll`** → a crashed run resumes without ever re-posting a question, and per-question answers are journaled so a crash mid-test never loses scores.
3. **Frozen paper (`prebuild`)**: at window-open the day's questions are read once (sheets/Mongo) and stored in the journal — the announce and polls then run off that snapshot, so a mid-day sheet edit cannot change a running exam. A day whose paper was frozen but never ran advances the cursor (consistent with "a missed slot stays missed"; ~0.7% of a volume).
4. **Preflight rights check before every announce** (see §2) — never announce into a chat we can't post in.
5. **Truncation, not skipping**: options >100 chars are truncated and, if two would collide, tagged `[A]/[B]…` so all 5 choices stay distinct (12 future AFO sets hit this; zero hard failures across all 2500 bank questions). Poll questions capped at 292 chars (+`25/50. ` prefix < 300).
6. **Countdown edits every 10s** in the last 60s (Telegram per-group send limits) instead of every second.
7. **>1 MB journal safety**: the GitHub Contents API stops returning bodies above 1 MB (≈2 weeks of journal at ~70 KB/day). `jload` falls back to the blobs API and `jsave` auto-switches to blob→tree→commit→ref once the file passes 700 KB — otherwise the whole journal would have silently died mid-October.
8. **Missed AFO day releases its set** back to `ready` (unused) so the bank audit stays truthful; the date is still sealed and never retro-fired.

## 6. FLAGS / OPEN ITEMS (no action taken without your order)

1. **Render paid bot is SUSPENDED** — `curl https://afo-daily-paper-06-pmm-1.onrender.com/` → `HTTP 503` body: *"This service has been suspended by its owner."* Keepwarm ping chal raha hai (150s), **redeploy nahi kiya** (paid.db wipe risk — Atlas migration not approved). JOIN-NOW flow is down until you un-suspend it.
2. **`CHAT_ID` secret ≠ locked group**: the live log shows `WARN chat_for(): CHAT_ID='***' != locked '-1003784795446' -> using locked value` (GitHub masks the secret, so I can't see its value). Engine is **locked** to -1003784795446 for all tests by design — please fix the secret so the warning goes away and no future code path trusts the wrong chat.
3. **Actions minutes**: measured on real runs — 37.5 billed minutes in the first 35 minutes (keepwarm 3.5 min/run, guard 4.8 min/run, chain 2.7 min/run) ⇒ **≈1,500 min/day ≈ 45,000 min/month** on a private repo. That is the cost of the locked cadences (guard ~7 min, keepwarm ~150s, chain jitter 100–190s). One-line dials if you want them: guard 7→15 min, keepwarm 150→600s, chain sleep 120–180→300–420 → ≈10–12k min/month. **I did not change the locked numbers.**
4. **Journal commit rate**: ~50–70 state.json commits per test (the crash-safety claim + 5Q checkpoints). Fine for the 1000 writes/hour API budget; it does make the commit list busy by design.
5. **13/14-Sep bank sets** (`set_no 1,2`) remain `ready`/unused — their dates are past. Say the word if you want them re-slotted to a spare date; otherwise they just sit there.
6. Old group messages (14-Sep announce #29092 + its polls) are **untouched** (still the group's pinned message). Unpin/delete only on your explicit order.
7. `AGENT.md`-style AI keys (Gemini/Groq/Mistral/OpenRouter) are in the vault but **no code path uses them** in this build — say the word if you want an AI question-bank builder (that would be a separate job, and the nemraj sheet now only has 11 rows).

## 7. HOW TO DRIVE IT

```
manual test now:      Actions → slot-chain → Run workflow                      (cycle runs, gates apply)
one job right now:    python3 engine/engine.py run iari                         (ignores window; debug only)
freeze tomorrow's:    python3 engine/engine.py prebuild malwa
what's scheduled:     python3 engine/engine.py status
rights gate:          python3 engine/engine.py ready
emergency stop:       Actions → slot-kill → Run workflow
book delivery:        Actions → booksend (manual only)  job=iari range=1-1074 step=5 chat=<id>
```
CTA in the group stays exactly one line: `🌾 Roz ka schedule: 11:00 AM Malwa Book · 2:30 PM IARI Book · 6:00 PM AFO Mains — @agriquizworld`
