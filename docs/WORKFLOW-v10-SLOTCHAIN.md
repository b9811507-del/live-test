# WORKFLOW v10 — SLOT-CHAIN (self-dispatched test scheduler) — 14-Sep-2026

## 0. Problem (aaj ka root cause, verified)
- GHA `schedule:` triggers is repo par ghanton late/skip hote hain (3 baar observe + aaj proof: enable ke baad bhi slot-malwa runs: []).
- `workflow_dispatch` + self-redispatch chain (keepwarm pattern) 4-min cadence pe KAM karta hai → scheduler authority cron se hatakar CHAIN banegi.

## 1. Schedule (user-confirmed today)
| Slot | Job | Time IST |
|---|---|---|
| Subah | malwa (Vol1→Vol2→Horti) | **11:00 AM** |
| Dopahar | iari | **2:00 PM** (user ne aaj 02:00 bola; code me ek jagah: JOBS["iari"]["hh/mm"]) |
| Shaam | afo mains (50Q, till 1-Nov) | **6:00 PM** |

## 2. Architecture — 4 agents, ek chain-of-purpose
```
keepwarm-agent (Render web alive, 4-min chain)      ── existing (rely mat karo slots ke liye)
slot-chain.yml   = MAIN test executor, self-chained ~3-min cycle    [NEW]
   └─ engine.py slotchain (per cycle, sab jobs):
       1. window [go-50min, go+4h] ke bahar → kuch nahi
       2. step0 aur window ke andar  → prebuild (translate warm, budgeted) → cmd_run (announce→countdown→polls→file→CTA→tomorrow)
       3. 0<step<8 (interrupted test) → cmd_run RESUME (journal se) — kabhi dobara announce nahi
       4. step0 aur now>go+4h        → MISSED, policy ke hisaab se skip (retrofire 4h ke andar allowed)
       5. end me: gh workflow run slot-chain.yml (self-redispatch) — cron ki koi dependency ZERO
   └─ timeout 240min; concurrency {group slot-chain, cancel:false} → test beech me KABHI kill nahi hoga
slot-guard.yml   = watchdog, self-chained ~7-min    [NEW]
   └─ slot-chain ka last run >25min purana? → force-dispatch slot-chain + DM admin "🛡 revived"
agents/doctor.py + engine.py agent (keepwarm pass)  ── failed GHA runs ko LLM se padhkar rerun/fix (existing, best-effort)
agents/sentinel.py                                  ── Render/bots health watchdog (existing)
```

## 3. Delivery routing (per-batch groups)
- `chat_for(job)` (live, tested): env `{JOB}_CHAT` set + quiz-bot us group me admin → test US group me; warna auto-fallback `@agriquizworld` + admin alert. Test kabhi nahi marta.
- Secrets ready: IARI_CHAT (-1003922097468). MALWA_CHAT/AFO_CHAT set karne ke liye bas @Malwaquiz_bot ko group admin chahiye (malwa me already hai — MALWA_CHAT secret set karte hi route ho jaayega).

## 4. State & idempotency
- state.json (git-committed by engine) = single source: days[date][job].step journal + ptr (book pages) + afo supply.
- Re-run/re-dispatch safe: complete steps skip; duplicate dispatch = idle pass.
- Pin policy v9: announce pinned, file unpinned; rotate_pins (2 pins/test max).

## 5. Old → New
- DELETE slot-malwa.yml, slot-iari.yml, slot-afo.yml (cron dead-weight; history git me safe).
- afo-supply.yml rahega (extra supply top-up; chain bhi due-day pe build() karta hai).
- Booksend relay step (keepwarm) → general `.GHA_DISPATCH.json` marker relay (kisi bhi workflow ko one-shot dispatch karne ke liye — seed ke liye use).

## 6. Failure handling (agent philosophy)
- Test crash mid-poll → resume se wahi se aage (journal). 2 crash baad bhi step<8 → agle cycle retry.
- Slot miss (chain poori mari thi) → 4h window ke andar ho to chalega, warna MISSED-forever (user rule: "missed slot stays missed").
- Chain dead → slot-guard zinda karta hai (independent chain) + dono ke runs GHA UI me dikhte hain.
- Har error ka admin DM: engine agent digest + guard revive notice + chat_for fallback alert.

## 7. Verification gates (likhne ke BAAD — done in same sitting)
- [x] py_compile engine; [x] YAML parse sab workflows
- [x] Fake-clock due-window matrix (10 cases, neeche log)
- [x] slot_go(14:00 IST) exactness
- [x] Seed push → marker relay → slot-chain first run live observe
- [ ] Live proof: next real slot me announce msg_id + step-journal advance (tonight 6PM AFO = first full live under v10)
