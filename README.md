# live-test — daily LIVE test system (AGRI QUIZ WORLD)

3 slots daily via @Malwaquiz_bot into @agriquizworld:
- ☀️ 11:00 IST MALWA books (Vol1→Vol2→Horti, strict 3 pages/day till done)
- 🌤 14:30 IST IARI BOOK MCQ 2026 (3 pages/day till done)
- 🌆 18:00 IST AFO MAINS new pattern (50Q · 30sec/Q · +2/−0.5 · till 1-Nov-2026)
Book marks: +1 / −0.25. Every slot: announce→countdown→test→full leaderboard→top3→offline file→Great Effort+JOIN CTA→tomorrow.

**Engine:** `engine/engine.py` (stdlib-only) run by GitHub Actions crons.
**State:** `state.json` committed by Actions — git is the database.
**Server:** `renderapp/app.py` on Render (`livescore`) — hosts locked test page, grades server-side (keys never sent to browser), /api/board.
**Self-healing agent:** keepwarm+agent workflow every 10 min: health-checks Render, re-runs failed Actions, resumes any unfinished slot (journal steps in state.json), DMs digest to admin.
Secrets: TG_TOKEN, CHAT_ID, RENDER_URL, ADMIN_KEY, ADMIN_CHAT(optional).
