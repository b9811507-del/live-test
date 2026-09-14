# Multi-Book / Multi-Group Delivery Workflow

Status: DESIGN ONLY — approved by user on 2026-09-10? No. Waiting for "GO".
All facts below were verified live against Telegram + Google on 2026-09-10.

## 1. Jobs (one book = one job = one manifest + one state file)

| # | job id    | book title (LIVE from sheet name)      | group                     | chat_id           | Q     | pages     | est. batches (5-page) | est. send time |
|---|-----------|----------------------------------------|---------------------------|-------------------|-------|-----------|-----------------------|----------------|
| 1 | malwa_vol1| MALWA BOOK VOL 1                       | Malwa Book Quiz           | -1003761821341    | 2,039 | 1–466     | ~93                   | ~6 min         |
| 2 | malwa_vol2| MALWA VOL 2                            | Malwa Book Quiz           | -1003761821341    | 2,842 | 1–406     | 82                    | ~5 min         |
| 3 | malwa_hort| MALWA HORTICULTURE                     | Malwa Book Quiz           | -1003761821341    | 1,260 | 1–180     | 36                    | ~2.5 min       |
| 4 | rksharma  | R.K.SHARMA BOOK 22TH EDITION (strip)   | RK sharma Quiz            | -1003880198347    | 4,564 | 1–662     | 133                   | ~9 min         |
| 5 | iari      | IARI BOOK MCQ 2026                     | (IARI group — BLOCKED)    | -1005569600848?   | 7,448 | 1–1074    | 215                   | ~14 min        |

- Bot for ALL five jobs: @MCQBYBOOK_bot (8578624305:…) — `getMe` OK.
- Sent as: one document per batch + its caption, then PIN. Order = table order.
- Nemraj job (90 batches, 3,108 Q, index) stays exactly as delivered; untouched.

### Verified on 2026-09-10
- All 5 sheets export via public CSV link (no auth). All 5 have the same 11 columns:
  `Serial No, Book Page, Topic, Question, Option A–E, Correct Answer, Explanation`.
- Groups seen by bot: "Malwa Book Quiz" ✅ member, "RK sharma Quiz" ✅ member.
- **IARI chat `-1005569600848` → `Bad Request: chat not found`**: the bot is NOT in that
  group yet. Job 5 is blocked until SatyamSir adds @MCQBYBOOK_bot and promotes it to admin
  (Post messages + Pin messages). The id itself is inferred from the invite link the same
  way Nemraj's was (`#-5569600848 → -1005569600848`); adding the bot confirms it instantly.

## 2. Book title rule (user's standing requirement)
`--book auto`: the sheet's live name is scraped at build time (Drive `og:title`) and used
EVERYWHERE — landing page, `<title>`, captions, index header. If the sheet is renamed later,
the next `rebuild` picks the new name automatically. If a `--book` is supplied and differs
from the live sheet name → build aborts. Trailing spaces in sheet names are stripped.

## 3. Per-job pipeline (identical for all 5 jobs)

```
plan   = rig.plan(rows, pages_per_batch=5)          # strict 5-page windows, block never split
build  = build_all.py --url <sheet> --out out/<job>/ --pages-per-batch 5 --book auto
verify = node test/final.js  (3 sampled batches)   # must be 88/88 before anything is sent
send   = telegram.py send --all --job <job>         # per batch: sendDocument (caption) → pinChatMessage
index  = telegram.py index --job <job>              # book-style TOC, Join = deep link to batch msg
state  = out/<job>/sent.json                         # one line per batch: fp, msg id, pinned?
```

- Caption format (fixed, English, no timer): `📗 <BOOK>` / `Pages a–b · N MCQs` / `Topic` / `By SatyamSir` / offline note.
- 429 flood-wait is handled by the transport (retry_after + backoff), gap 1.4 s + pin gap 2 s.
- Resume: a batch is skipped iff its content fingerprint + template match the last success.
  Re-running after any crash sends nothing twice and skips nothing.

## 4. Sheet-data sanity (new, discovered while verifying)

1. **Book Page can be a RANGE** — MALWA VOL 1 stores `1-2`, `3-4` … (one block of Qs per
   page-pair). Parser must accept `int` AND `lo-hi`. A block is placed in the 5-page window
   containing its HIGH number, labelled `Page No. lo-hi`, and never split.
2. **VOL 1 typos**: 3 blocks (22 rows) read `5-340`, `8-540`, `9-573` — impossible spans.
   Auto-rule: use `hi-1 – hi` (fits serial order and both neighbours). Report printed before
   sending. (If SatyamSir fixes them in the sheet instead — even better, nothing to do.)
3. Rows where `Question` is empty (merged topic headers etc.) are skipped — verified VOL 1
   has exactly 1 such row with data, and it is a topic header only.
4. Guard: if > 25 % of rows parse to page 0/blank → ABORT with a report, never build a
   giant "page 0" batch (that is what almost happened before this rule existed).

## 5. Index per group ("book feel", same as approved Nemraj demo)

- One index per job (per book), HTML parse, everything bold, `📖 TITLE 📖` / `By SatyamSir`
  / gap / `1. Page No. 1-5  🔗 Join` … 30 lines per message, `Next ➡️ / ⬅️ Previous` between
  index pages, all pinned, pin order reversed so **page 1 sits on top of the pin bar**.
- `🔗 Join` = `https://t.me/c/<group>/<message_id>` deep link → tap jumps straight to that
  batch's file message.
- Malwa gets 3 indexes (VOL 1, VOL 2, HORTICULTURE) in that order, after each book's batches;
  after all three finish, re-pin VOL 1 index page 1 → header TOC = VOL 1 (list has all).
- If a book's sheet changes later: rebuild → re-run `index` → old index pages deleted,
  new ones sent+linked automatically.

## 6. Code that must be written for this (after GO only — nothing exists yet)

| change | file | size |
|---|---|---|
| `--out out/<job>/` + per-job manifest/state paths | build_all.py, telegram.py | small |
| `jobs.json` = the table in §1 (sheet id, chat id, order) | new file | 6 lines |
| page parser: `int` \| `lo-hi` block + page-0 abort | rig.py | ~15 lines |
| typo auto-fix `hi-1–hi` + report | rig.py | ~10 lines |
| `bookjob.py run-all` = the unattended chain (§7) | new file | ~60 lines |

## 7. Unattended run ("laptop band karne par bhi kaam hoga?")

- `python3 bookjob.py run-all` is launched as ONE background process in the cloud sandbox.
- The user's laptop is only a viewer — nothing routes through it. Closing it cannot pause
  the run. Progress: `out/<job>/sent.json` after every single message + `out/<job>/run.log`.
- Failure semantics: API error after retries → that batch marked failed, loop continues;
  at the end the log says exactly `sent / failed / pending`. Any later re-run resumes.
- Expected wall clock: ~45–60 min for jobs 1–4 (~450 messages). Job 5 whenever the bot is in.

## 8. What SatyamSir must do (only these)

1. Add **@MCQBYBOOK_bot** to the IARI group → promote to admin → allow **Post messages + Pin messages** (needed for every group, once).
2. Say **GO**. (Optional: fix or ignore the 3 VOL-1 typo blocks — the auto-rule covers them.)

## 9. Acceptance bar

- Group message counts match: every batch sent AND pinned AND caption page-range correct.
- Index: every line's Join opens the right batch message.
- No duplicate messages, no double sends after a crash/resume.
- 88/88 final.js on sampled batches per book; selftest 24/24 stays green.
