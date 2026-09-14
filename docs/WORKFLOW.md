# NEMRAJ MCQ Rig — Natural-language bot workflow (design, not code)

Goal: SatyamSir group me normal bhasha me baat kare — "page 40–50 ka batch bhej do",
"grp ki new id ye hai: -100xxxx" — bot samjhe, kaam kare, aur result bataye.
Commands yaad rakhne ki zaroorat nahi.

---

## 1. Golden rule: LLM sochta hai, code karta hai

```
your message
    ↓
[CONTEXT]  manifest + state + config + last 20 turns
    ↓
[LLM]      decides ONE of: {reply | ask-a-question | call-a-tool}
    ↓
[GATE]     tool name + args schema se validate  ← LLM yahan rukta hai
    ↓
[EXEC]     deterministic actions only (build_all / rig plan / telegram send / config write)
    ↓
[RESULT]   structured JSON (ok, ids, counts, errors)
    ↓
[LLM]      result ko 2-4 line me human language me translate karke reply
```

**The LLM never writes files, never builds HTML, never runs python, never edits the sheet.**
It only picks a tool name + arguments from a fixed list. Agar wo kuch unknown maange → gate
reject karta hai, aur bot aapko honestly bolta hai ki ye mere bas se bahar hai.

### Why this shape
* Batches/pin/rate-limits determinism maangte hain — LLM ko loop me mat daalo.
* Ek galat "creative" action 64 files group me pin kar sakta tha. Gate usko rokta hai.
* Model badalna safe ho jaata hai (infra fixed, sirf brain swap).

---

## 2. Tool catalog (the ONLY verbs the bot can use)

| tool | kya karta hai | args | risky |
|---|---|---|---|
| `deliver_next` | next pending batch(es) bhejo + pin | `count` (1–10) | yes (posts) |
| `deliver_range` | pages X–Y ka fresh batch banao, bhejo, pin | `pages`, `topics?`, `target?` | yes |
| `rebuild_all` | poora book dobara render (content/template change ke baad) | `force?` | no (local) |
| `sheet_check` | live sheet vs manifest compare: added/changed/removed Q, new pages | — | no |
| `config.set` | **whitelisted keys only** + validator (chat_id / bot_token / target / spb / brand / admin_ids / pin_phrase / sheet_url / gid) — free-text writes nahi | `key`, `validated value` | yes (writes config) |
| `forget_sent` | batch ko "pending" wapas karo (dobara bhejne ke liye) | `ids` | yes |
| `status` | kitna gaya, kitna bacha, aakhri bhatke | — | no |
| `preview` | caption/diff dikhao, kuch mat bhejo | `ids` or `pages` | no |
| `undo_last` | last pin hatao (file delete nahi, Telegram pin unpin) | — | yes |
| `abort` | chal rahi send queue roko | — | no |

Har tool ka output fixed JSON: `{"ok":…, "did":…, "summary":…, "errors":[…]}` —
yaani LLM ko hamesha sach milta hai, apni kahani banane ki zaroorat nahi.

**Missing / impossible tools (by design), and what the bot will say instead:**
* sheet **edit** (naya question daalna) → sheet aapki Google account me hai, bot ke paas edit
  rights nahi (public link = read-only). Bot: *"sheet me row add kar dijiye, phir 'sheet check
  karo' boliyega — main naye questions ka batch bana dunga."* (Agar aap future me service
  account share kar do, `sheet_write` tool add ho sakta hai — that's a decision, see §8.)
* group **settings** change (naam, members) → Telegram bot API allowed nahi; bot sirf
  `chat_id` badal sakta hai (apni config me).
* kisi ka phone/test result padhna → students ka score device ke **localStorage** me rehta hai,
  server par kuch nahi. Future option: HTML file me "send my result to bot" button (needs design).

---

> **Update:** brain layer ka exact design (`decision` schema, slot resolution, 4 verdicts,
> config whitelist, sheet-change branches) ab [`agent/BRAIN.md`](agent/BRAIN.md) me hai —
> wo §2/§3 ko supersede karta hai. Yahan rig/delivery level ka design hai.

## 3. Intent → tool, with real phrasing examples

| Aap keh sakte ho (koi bhi tarah) | Bot samjhega |
|---|---|
| "bhej do" / "next" / "aage badho" | `deliver_next count=1` |
| "5 batch ek saath bhej de" | `deliver_next count=5` (confirm pehle) |
| "page 40 se 50 ka naya batch bana ke bhejo" | `deliver_range pages=40-50` |
| "sirf entomology wale page 100–120" | `deliver_range pages=100-120 topics=Entomology` |
| "grp ka id badal ke -1009876 karo" | `set_config chat_id=-1009876` + `check` + report |
| "ab token ye hai 123:ABC" | `set_config token=…` (token masked echo hoga) |
| "sheet me 3 naye question add kiye hain" | `sheet_check` → kya-naya batayega → "batch banaun?" |
| "template update hua hai, sab dobara bana do" | `rebuild_all` → phir pending list |
| "kal tak kitna chala gaya?" | `status` (state file ke timestamps se) |
| "B007 galti se double chala gaya, wapas pending karo" | `forget_sent ids=B007` |
| "jo abhi bheja tha wo pin hata do" | `undo_last` |
| "pehle dikha kya bhejne wale ho" | `preview` |
| "ruk jao" (queue ke beech) | `abort` |
| Kuch ambiguous / 2 batches ka doubt | **ask** — 1 clarification question, phir kaam |

Rules: numbers (pages, ids, counts) model ko guess nahi karne — config ya sheet se
resolve karke wapas dikhaye jaate hain. E.g. "agla page" → bot current max page se compute karta hai.

---

## 4. Confirmation gates (safety, non-negotiable)

1. **Write-action = 2-step** jab scale badi ho: `count>=3`, `deliver_range` >80 questions, ya
   `rebuild_all` — bot pehle plan dikhayega (*"6 batches, 288 Q, group me pin honge — confirm?"*),
   yes/haan/ok aane par hi execute.
2. **`chat_id` change** → bot turant `check` chalega (getMe + getChat + admin/pin test) aur
   group ka **title** aapko dikhaayega: *"new chat = 'Agri Batch 2' — is group me bhejun?"*
   (Galat id par 64 files bhejna actual disaster hai.)
3. **Never re-pin silently**: har batch ka fingerprint + message_id state me hai.
4. **Rate limits**: 1 doc / 1.4 s, pin ke baad 2 s, HTTP 429 → `retry_after` respect,
   backoff; queue background me chalta hai taaki aapke beech ke messages block na hon.
5. **Admin-only**: group ke current admins (getChatAdministrators) + optional `admin_ids` allowlist;
   non-admin ko sirf `status`/`preview` (read-only) ya "not for you".
6. **Kill switch**: aap "ruk jao" / `/stop` bolo → queue cancel, progress state me safe.
7. Optional second factor: config me `pin_phrase` rakho → koi bhi write action us phrase ke
   bina reject (agar group me aur log admin ho jaayein).

---

## 5. Memory / state (kya-kya yaad rahega)

```
out/manifest.json   batch plan + fingerprints      (build time)
out/sent.json       id → {fp, at, message_id, pinned, skipped}
out/jobs.log        every run: what was sent, errors, who asked (append-only JSONL)
telegram.json       token, chat_id, target, spb, brand, admin_ids, pin_phrase?
out/sheet.csv       last fetched snapshot (for diffs)
```
Bot "yaad" inhi files se karta hai — LLM memory pe bharosa nahi. Session reload ke baad bhi
"last kya hua tha?" ka jawab exact aata hai. Optional: `out/chatlog.jsonl` me last N turns
(privacy: sirf commands + summaries, student data nahi).

---

## 6. LLM provider + the "dumb-mode" fallback

* **Pluggable provider**: koi bhi OpenAI-compatible endpoint (base_url + api_key + model).
  Recommendation: tool-calling capable model, low latency, temperature 0.
* **Structured output**: function/tool schema se — free text JSON nahi maangenge.
* **Dumb mode (important)**: LLM API down/timeout → bot ek rule-based parser pe gir jaata hai
  (regex intents: bhej/send/next/page X-Y/id change/status). Yaani *core delivery kabhi nahi rukti*,
  LLM sirf smarts ke liye hai, dependency ke liye nahi.
* Budget: per message ≈ 1–2 small calls (decide + summarise). Long group chat ko we
  summarize-karke context chhota rakhenge (last 20 turns, not full history).

---

## 7. Failure handling (real cases)

| Hua | Bot kya karega |
|---|---|
| File bhej di, pin fail (bot admin nahi) | file sent mark karo, *pin error* clearly report, retry pin only |
| 429 flood limit | queue pause, retry_after ke baad continue, aapko "3 s wait" dikhao |
| Sheet me page 500 tak pahunch gaya | `status`: "all 64 batches delivered ✅ — naya content chahiye to sheet_check" |
| Sheet row edit/delete | `sheet_check` diff: `page 44: 2 changed, 1 removed` → rebuild only affected batches |
| Build 0 questions return kare | gate: kuch bhi mat bhejo, reason batao (filter typo, page numbers as text, etc.) |
| Duplicate send request (aap 2 baar "bhej do") | state check → "B007 already delivered at 21:14; bhejun phir se? (yes to force)" |
| Bot restart mid-queue | resume from `sent.json` (already-sent skip) |
| Galat chat_id | `check` fail on getChat → refuse to send anything |

---

## 8. Decisions I need from you (baaki main kar lunga)

1. **LLM provider + key** — kaunsa endpoint use karein? (Aap key denge, ya main ek pluggable
   config chhod doon jisme aap baad me daal denge?)
2. **Confirmation strictness** — sirf bade actions pe confirm (recommended), ya har group post pe?
3. **Where it runs** — 24×7 ek server/VPS par (recommended, kyunki bot ko live messages
   chahiye), ya aap machine par? (Sandbox me main demo/test kar sakta hoon but permanent hosting nahi.)
4. **Admin policy** — sirf aap, ya group ke saare admins? `pin_phrase` second factor on/off?
5. **Sheet edits** — bot read-only rahe (recommended), ya aap ek service account ko sheet ka
   editor bana ke `sheet_write` (future me) enable karna chahenge?
6. **Student results** — abhi device-local (kuch nahi aayega). Chahiye to `submit result` button
   wala design alag se karenge (group me scores ka privacy angle bhi sochna hoga).

---

## 9. Build order (code isme hi aayega, once approved)

1. `agent/context.py` — manifest/state/config reader + `describe_state()` (LLM ko dene wala snapshot)
2. `agent/tools.py` — the 10 verbs, pure functions, JSON in/out, no LLM anywhere
3. `agent/gate.py` — schema validation, confirmation ledger, admin check, rate limiter
4. `agent/llm.py` — provider wrapper (tool-calling, timeouts, structured args) + rule-based fallback
5. `agent/loop.py` — Telegram long-poll → context → LLM → gate → tool → summarize → reply (+ queue)
6. `agent/selftest.py` — mock Telegram + mock LLM: **24 scenarios** (upar ki har row of §7 included),
   plus a **dry-run rehearsal** where every real action is executed against a private test group
7. Ship: run in `--listen` mode; `status`/`preview` first, live sending after your 👍

Acceptance: main tab tak "done" nahi bolunga jab tak (a) selftest 24/24, (b) ek real dry rehearsal
private group me, (c) aapke 3 natural-language test phrases sahi tool pe map ho — teeno na dikhein.
