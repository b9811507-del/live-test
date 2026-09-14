# FRESH ENGINE — TERMS (locked one by one; none may change without admin order)

## T1 — TIMEZONE ✅ LOCKED 2026-09-14
- Every clock, label, journal day-key, slot window, file name = **IST (Asia/Kolkata), UTC+5:30**.
- "Day" = IST calendar date. No UTC dates anywhere user-facing. `TZ=Asia/Kolkata` in every workflow; engine computes IST directly (never trusts host clock).

## T2 — DAILY SCHEDULE ✅ LOCKED 2026-09-14
| Slot | IST | Series (locked order) |
|---|---|---|
| Morning | **11:00 AM** | MALWA VOL 1 → khatam hone par VOL 2 → khatam hone par MALWA HORTICULTURE → series khatam ⇒ malwa slot band (congrats pinned) |
| Noon | **2:30 PM** | IARI BOOK MCQ 2026 |
| Evening | **6:00 PM** | AFO FULL-LENGTH TEST |
- Window: start allowed from **go−50 min**; a missed slot stays missed till **go+4h**, never retro-fired.
- Book rotation: engine picks current volume by journal `bidx`; volume exhausted (all its question rows used) → next volume begins next IST day automatically.

## T3 — FRESH BUILD ✅ LOCKED 2026-09-14
- No restore of old code. New files, new root commit(s) in private repo `b9811507-del/live-test` (repo = keys vault: 16 GHA secrets stay).
- Re-carried admin rules (they are ORDERS, not old code): 30s/question · +1 right / −0.25 wrong (AFO: its own pattern) · 4-line announce, pinned · polls unpinned · leaderboard 48 rows/msg · congrats pinned · 6065-format result FILE sent **unpinned** · short CTA after file · resume-by-journal, never re-announce · ONE data copy (no duplicate posts, delete superseded copies) · NOTHING posted to any group without explicit admin order (booksend-style jobs = manual dispatch only) · state.json in git = single database.

## T4 — DATA SOURCES ✅ LOCKED 2026-09-14 (Mongo fresh-fixed: 50/50 sets ready)
- malwa_vol1  = Google Sheet `128DIQLjlO0FfsTUReGbr2sHJcaJDg6WLjJc7CVRpNhg`
- malwa_vol2  = Google Sheet `1UgnIe-g8Fh0GiwtbQpSHgtlVtPk2hEngzBW5idqFD_E`
- malwa_horti = Google Sheet `1YcJWVgWofbLkzOGeeDuPke7XPpyW_EETn9LeEEuz_dE`
- iari        = Google Sheet `1sUgWskoLr7U16kVtKWb1o5-GItSv5UPumD9VCH3T4NI` (≈1074 pages)
- afo         = MongoDB Atlas bank (secret `MONGO_URI`), topped daily 05:00 IST by supply job; no-repeat audit enforced at draw.
- QUESTION SOURCE RULE: read-only from these; engine never edits sheets.

## T5 — ROUTING ✅ LOCKED 2026-09-14
ALL THREE tests run in **@agriquizworld (-1003784795446)** using **only** bot @Arunkatyanquiz_bot (secret `EXAM_TG_TOKEN`; admin in group ✓; stale Render webhook removed ✓). IARI/AFO paid-group routing DROPPED by admin order.
- malwa → free group @agriquizworld (`CHAT_ID` = -1003784795446) ✅ (as today)
- iari  → paid IARI group (`IARI_CHAT`) — ⚠ quiz bot @Malwaquiz_bot ko wahan admin add karna admin ka kaam hai; tab tak fallback: @agriquizworld + admin DM
- afo   → ❓ KAUNSE group me? (AFO group ka chat-id + bot admin chahiye; warna fallback @agriquizworld)

## Build order (ek turn = ek stage, admin "next" par hi agla)
1. config+journal → 2. sheet/mongo readers → 3. exam flow (announce→polls→LB→file→CTA) → 4. slot-chain scheduler + guard → 5. kill/relay/keepwarm → 6. verification battery (fake-clock matrix + compile + YAML) → 7. enable + live proof.
