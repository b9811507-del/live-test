#!/usr/bin/env python3
"""v11.4.7 — admin corrections after watching a live run:

(1) NO reveal message after each question any more ("hr question kai bd yh nhi aana chhiye"). The
    explanation already travels inside the quiz poll (v11.4.6), so the student sees correct/wrong +
    explanation the moment they answer; the group is not spammed with N extra messages.
(2) The leaderboard must arrive COMPLETE ("leaderboard complete aana chhiye"). It is now split by
    *rendered length* (never by a fixed row count + truncation), every part is < 4096 chars, each row
    is whole, parts are paced ~1.1 s apart, failures resume on the next cycle, and the rest of the
    post-test flow waits until every part has landed.
(3) The daily-schedule sign-off line is gone ("yh message bhi nhi aaana chhaiye"); tomorrow's plan
    message (pages / full schedule) stays.

Final post-test order: leaderboard (all parts) -> TOP 3 -> HTML file -> tomorrow's plan. Nothing else.
"""
import io

E = "engine/engine.py"
s = io.open(E, encoding="utf-8").read()
n0 = len(s)

# ---------------------------------------------------------------- 1. config switches
old = '''POLL_MODE = (os.environ.get("POLL_MODE", "quiz") or "quiz").strip().lower()   # quiz = explanation in the poll'''
new = '''POLL_MODE = (os.environ.get("POLL_MODE", "quiz") or "quiz").strip().lower()   # quiz = explanation in the poll
REVEAL_AFTER_Q = (os.environ.get("REVEAL_AFTER_Q", "off") or "off").strip().lower() in ("on", "1", "yes")
CTA_SHOW = (os.environ.get("CTA_SHOW", "off") or "off").strip().lower() in ("on", "1", "yes")
LB_MSG_LIMIT = int(os.environ.get("LB_MSG_LIMIT", "3900"))       # Telegram message limit is 4096'''
assert old in s, "poll mode anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 2. leaderboard: head / row / parts
old = '''def leaderboard_text(day, job, plan, rows, part=0):
    cfg = JOBS[job]
    label = plan.get("label") or job.upper()
    head = (tr.t("lb_head", label=esc(label), n=plan["n"], right=fmt_num(cfg["right"]),
                 wrong=fmt_num(abs(float(cfg["wrong"]))))
            if part == 0 else tr.t("lb_head_contd", label=esc(label)))
    if not rows:
        return head + "\\n\\n" + tr.t("lb_empty")
    out = [head, ""]
    for r in rows:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"]) or ("#%d." % r["rank"])
        out.append("%s <a href=\\"tg://user?id=%s\\"><b>%s</b></a> — <b>%+.1f</b> · %d correct · %d incorrect"
                   % (medal, esc(r["uid"]), esc(r["name"]), r["score"], r["right"], r["wrong"]))
        if part == 0 and r["rank"] <= 3:
            out.append("")            # breathing room under the medal rows
    return "\\n".join(out)'''
new = '''def lb_head_text(day, job, plan, part=0):
    cfg = JOBS[job]
    label = plan.get("label") or job.upper()
    return (tr.t("lb_head", label=esc(label), n=plan["n"], right=fmt_num(cfg["right"]),
                 wrong=fmt_num(abs(float(cfg["wrong"]))))
            if part == 0 else tr.t("lb_head_contd", label=esc(label)))


def leaderboard_row(r):
    """One student's line: medal/rank + tap-able name + score + correct/incorrect."""
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"]) or ("#%d." % r["rank"])
    return ("%s <a href=\\"tg://user?id=%s\\"><b>%s</b></a> — <b>%+.1f</b> · %d correct · %d incorrect"
            % (medal, esc(r["uid"]), esc(r["name"]), r["score"], r["right"], r["wrong"]))


def leaderboard_text(day, job, plan, rows, part=0):
    head = lb_head_text(day, job, plan, part)
    if not rows:
        return head + "\\n\\n" + tr.t("lb_empty")
    out = [head, ""]
    for r in rows:
        out.append(leaderboard_row(r))
        if part == 0 and r["rank"] <= 3:
            out.append("")            # breathing room under the medal rows
    return "\\n".join(out)


def leaderboard_parts(day, job, plan, rows):
    """v11.4.7: split the leaderboard so EVERY student is listed exactly once and no message is ever
    truncated. Packing is by rendered length (<= LB_MSG_LIMIT), not by a fixed row count."""
    if not rows:
        return [leaderboard_text(day, job, plan, [], part=0)]
    head0 = lb_head_text(day, job, plan, part=0)
    cont = lb_head_text(day, job, plan, part=1)
    parts, cur, size, first = [], [head0, ""], len(head0) + 1, True
    for r in rows:
        line = leaderboard_row(r)
        add = len(line) + 1 + (1 if r["rank"] <= 3 else 0)
        if size + add > LB_MSG_LIMIT and len(cur) > 2:
            parts.append("\\n".join(cur))
            cur, size, first = [cont, ""], len(cont) + 1, False
        cur.append(line)
        if r["rank"] <= 3:
            cur.append("")
        size += add
    parts.append("\\n".join(cur))
    for p in parts:
        assert len(p) <= 4096, "leaderboard part too long (%d)" % len(p)
    return parts'''
assert old in s, "leaderboard_text anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 3. run_job: send every part, wait until complete
old = '''    rows = score_rows(day, job, plan, ans, names)
    if not j.get("lb_sent"):
        for part, i in enumerate(range(0, max(len(rows), 1), LB_ROWS)):
            txt = leaderboard_text(day, job, plan, rows[i:i + LB_ROWS], part)
            tg("sendMessage", chat_id=chat, text=txt[:4000], parse_mode="HTML", disable_web_page_preview=True)
        j["lb_sent"] = True
        j["step"] = 4
        j["players"] = len(rows)
        j["answered_total"] = sum(len(v) for v in ans.values())
        jsave(st, "%s leaderboard" % job)'''
new = '''    rows = score_rows(day, job, plan, ans, names)
    if not j.get("lb_sent"):
        parts = leaderboard_parts(day, job, plan, rows)
        done = int(j.get("lb_parts_sent") or 0)
        if done >= len(parts):
            done = 0                                  # journal from an older run -> re-send everything once
        for k in range(done, len(parts)):
            m = tg("sendMessage", chat_id=chat, text=parts[k], parse_mode="HTML",
                   disable_web_page_preview=True)
            if not m:
                log("leaderboard part %d/%d FAILED -> the rest of the flow waits, next cycle resumes here"
                    % (k + 1, len(parts)))
                break
            j["lb_parts_sent"] = k + 1
            jsave(st, "%s leaderboard %d/%d" % (job, k + 1, len(parts)))
            log("leaderboard part %d/%d sent (players listed so far: %s)"
                % (k + 1, len(parts), min(len(rows), k * 40 + 40)))
            time.sleep(1.1)                           # gentle pacing (group flood limits)
        if int(j.get("lb_parts_sent") or 0) < len(parts):
            j["locked_by"] = ""
            jsave(st, "%s leaderboard incomplete (will resume)" % job)
            return "leaderboard-partial"
        j["lb_sent"] = True
        j["lb_parts"] = len(parts)
        j["lb_rows"] = len(rows)
        j["step"] = 4
        j["players"] = len(rows)
        j["answered_total"] = sum(len(v) for v in ans.values())
        jsave(st, "%s leaderboard complete (%d part(s))" % (job, len(parts)))'''
assert old in s, "leaderboard send anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 4. reveals off by default
old = '''        # v11.4: native-quiz-bot style reveal (correct option + explanation + who was right)
        try:
            rv = tg("sendMessage", chat_id=chat, text=reveal_text(job, plan, i, q, aq, names),
                    parse_mode="HTML", disable_web_page_preview=True)
            if rv:
                j["reveals"] = int(j.get("reveals", 0)) + 1
        except Exception as e:
            log("reveal failed for Q%d: %s" % (i + 1, str(e)[:90]))'''
new = '''        # v11.4.7 (admin order): NO reveal message after each question — the explanation is already
        # inside the quiz poll, so students see correct/wrong + explanation instantly. REVEAL_AFTER_Q=on
        # brings the separate message back if ever needed.
        if REVEAL_AFTER_Q:
            try:
                rv = tg("sendMessage", chat_id=chat, text=reveal_text(job, plan, i, q, aq, names),
                        parse_mode="HTML", disable_web_page_preview=True)
                if rv:
                    j["reveals"] = int(j.get("reveals", 0)) + 1
            except Exception as e:
                log("reveal failed for Q%d: %s" % (i + 1, str(e)[:90]))
        else:
            j["expl_in_poll"] = int(j.get("expl_in_poll", 0)) + (1 if (q.get("expl") and POLL_MODE == "quiz") else 0)'''
assert old in s, "reveal anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 5. CTA off by default
old = '''    if not j.get("cta_sent"):
        c = tg("sendMessage", chat_id=chat, text=cta_text(), parse_mode="HTML", disable_web_page_preview=True)
        if c:
            j["cta_sent"] = c["message_id"]'''
new = '''    # v11.4.7 (admin order): the daily-schedule sign-off line is not posted any more.
    if CTA_SHOW and not j.get("cta_sent"):
        c = tg("sendMessage", chat_id=chat, text=cta_text(), parse_mode="HTML", disable_web_page_preview=True)
        if c:
            j["cta_sent"] = c["message_id"]
    elif not CTA_SHOW and not j.get("cta_sent"):
        j["cta_sent"] = "off"'''
assert old in s, "cta anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- 6. journal order
old = '''    j["msg_order"] = ["announce", "countdown", "polls+reveals", "leaderboard", "top3", "file", "tomorrow-plan", "cta"]'''
new = '''    j["msg_order"] = ["announce", "countdown", "quiz-polls(+in-poll explanation)", "leaderboard(all parts)",
                      "top3", "file", "tomorrow-plan"]'''
assert old in s, "msg_order anchor not found"
s = s.replace(old, new, 1)
io.open(E, "w", encoding="utf-8").write(s)
print("v11.4.7 applied (%d -> %d chars)" % (n0, len(io.open(E, encoding="utf-8").read())))
