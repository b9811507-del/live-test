#!/usr/bin/env python3
"""One-shot patch part 2: v11.1 behaviour
  * announce -> 15s countdown -> polls (no more 60s pre-start edits)
  * paid-batches message = LAST message after each test
  * desk pass (student DMs, payments, single-use join links) inside keepwarm
  * early runs defer (re-arm only), poller keeps Telegram's allowed_updates stable
  * polls carry an English topic tag (educational), result file in English
Run from repo root: python3 tools/patch_v11_1b.py
"""
import sys

P = "engine/engine.py"
s = open(P, encoding="utf-8").read()
orig = s

ANNOUNCE_OLD = '''    # --- step 1: announce once (pinned)
    if int(j.get("step", 0)) < 1:
        m = tg("sendMessage", chat_id=chat, text=announce_text(job, day, plan), parse_mode="HTML",
               disable_web_page_preview=True)
        if not m:
            raise EngineError("announce failed for %s (check bot admin rights)" % job)
        j["msg_ann"] = m["message_id"]
        j["announced_at"] = istnow().isoformat(timespec="seconds")
        j["step"] = 1
        p = tg("pinChatMessage", chat_id=chat, message_id=m["message_id"])
        j["pinned_ann"] = bool(p)
        if not p:
            dm_admin(tr.t("adm_pin", job=job.upper()), "pin:" + job, 6 * 3600)
        jsave(st, "%s announce #%s" % (job, j["msg_ann"]))
        log("announce %s msg=%s pinned=%s" % (job, j["msg_ann"], bool(p)))

    # --- countdown to go (only when polls have not started and we are early)
    if int(j.get("step", 0)) < 2:
        go = go_dt(day, job)
        last_edit, last_push = 0.0, time.time()
        while True:
            d2g = (go - istnow()).total_seconds()
            if d2g <= 0:
                break
            if time.time() - t_start > CD_MAX:
                log("countdown %s: budget out, starting now" % job)
                break
            if j.get("msg_ann") and d2g <= 61 and (time.time() - last_edit) >= 10:
                tg("editMessageText", chat_id=chat, message_id=j["msg_ann"], parse_mode="HTML",
                   text=countdown_text(job, day, plan, int(d2g)))
                last_edit = time.time()
            if time.time() - last_push > 100:
                j["lock_ts"] = time.time()
                j["locked_by"] = RUN_ID
                jsave(st, "%s heartbeat" % job)
                last_push = time.time()
            sleep(min(d2g, 8 if d2g > 61 else 2))
        j["step"] = 2
        j["started_at"] = istnow().isoformat(timespec="seconds")
        jsave(st, "%s polls start" % job)'''

ANNOUNCE_NEW = '''    SELF = sys.modules[__name__]
    # --- step 1: announce (pinned) ANNOUNCE_LEAD before start, then a COUNTDOWN_SECS countdown, then polls
    go = go_dt(day, job)
    if int(j.get("step", 0)) < 2:
        announce_at = go - dt.timedelta(seconds=ANNOUNCE_LEAD)
        # wait silently (heartbeating) until the announce moment
        while istnow() < announce_at and time.time() - t_start < CD_MAX:
            j["lock_ts"] = time.time()
            j["locked_by"] = RUN_ID
            jsave(st, "%s pre-announce heartbeat" % job)
            sleep(min((announce_at - istnow()).total_seconds(), 30))
        if int(j.get("step", 0)) < 1:
            m = tg("sendMessage", chat_id=chat, text=announce_text(job, day, plan), parse_mode="HTML",
                   disable_web_page_preview=True)
            if not m:
                raise EngineError("announce failed for %s (check bot admin rights)" % job)
            j["msg_ann"] = m["message_id"]
            j["announced_at"] = istnow().isoformat(timespec="seconds")
            j["step"] = 1
            p = tg("pinChatMessage", chat_id=chat, message_id=m["message_id"])
            j["pinned_ann"] = bool(p)
            if not p:
                dm_admin(tr.t("adm_pin", job=job.upper()), "pin:" + job, 6 * 3600)
            jsave(st, "%s announce #%s" % (job, j["msg_ann"]))
            log("announce %s msg=%s pinned=%s" % (job, j["msg_ann"], bool(p)))
        # wait until the exact start time (zero group traffic in between)
        while istnow() < go and time.time() - t_start < CD_MAX + ANNOUNCE_LEAD:
            j["lock_ts"] = time.time()
            j["locked_by"] = RUN_ID
            jsave(st, "%s countdown heartbeat" % job)
            sleep(min((go - istnow()).total_seconds(), 30))
        # v11.1: a single 15-second countdown, then the first poll
        anchor = max(go, istnow() + dt.timedelta(seconds=COUNTDOWN_SECS))
        ticks = sorted({x for x in (COUNTDOWN_SECS, 10, 5, 4, 3, 2, 1) if 0 < x <= COUNTDOWN_SECS}, reverse=True)
        for val in ticks + [0]:
            target = anchor - dt.timedelta(seconds=val)
            if istnow() < target:
                sleep((target - istnow()).total_seconds())
            if j.get("msg_ann"):
                tg("editMessageText", chat_id=chat, message_id=j["msg_ann"], parse_mode="HTML",
                   text=countdown_text(job, day, plan, val))
                j["cd"] = val
                j["lock_ts"] = time.time()
                jsave(st, "%s countdown %ds" % (job, val))
        j["step"] = 2
        j["started_at"] = istnow().isoformat(timespec="seconds")
        jsave(st, "%s polls start" % job)
        log("countdown %ss done -> polls start" % COUNTDOWN_SECS)'''

# ---------- poll question: English topic tag ----------
POLL_OLD = '''        poll = tg("sendPoll", chat_id=chat, question="%d/%d. %s" % (i + 1, N, esc(q["q"])), options=q["o"],'''
POLL_NEW = '''        q_body = esc(q["q"])
        topic = (q.get("topic") or "").strip()
        if topic:
            topic = tr.translate_safe(topic) if tr.needs_translation(topic) else " ".join(topic.split())
            if topic and len(q_body) + len(topic) + 12 <= 292:
                q_body = "[%s] %s" % (esc(topic[:40]), q_body)      # educational topic tag on every poll
        poll = tg("sendPoll", chat_id=chat, question="%d/%d. %s" % (i + 1, N, q_body), options=q["o"],'''

# ---------- keep the poller's allowed_updates stable (payment/join-request updates included) ----------
DRAIN_OLD = '''        r = tg("getUpdates", offset=off, timeout=1)
        res = r if isinstance(r, list) else (r or {}).get("result")'''
DRAIN_NEW = '''        r = tg("getUpdates", offset=off, timeout=1, allowed_updates=ALLOWED_UPDATES)
        res = r if isinstance(r, list) else (r or {}).get("result")'''
BASE_OLD = '''    r = tg("getUpdates", offset=-1, timeout=0)'''
BASE_NEW = '''    r = tg("getUpdates", offset=-1, timeout=0, allowed_updates=ALLOWED_UPDATES)'''

# ---------- after polls: hand the offset to the desk, then paid message last ----------
POLLEND_OLD = '''    j["step"] = max(int(j.get("step", 0)), 3)
    j["polled"] = int(j.get("qidx", 0))
    jsave(st, "%s polls done" % job)'''
POLLEND_NEW = '''    j["step"] = max(int(j.get("step", 0)), 3)
    j["polled"] = int(j.get("qidx", 0))
    j["last_off"] = off
    st.setdefault("desk", {})["offset"] = max(int((st.get("desk") or {}).get("offset") or 0), int(off))
    jsave(st, "%s polls done" % job)'''

PAID_OLD = '''    if not j.get("cta_sent"):
        c = tg("sendMessage", chat_id=chat, text=cta_text(), parse_mode="HTML", disable_web_page_preview=True)
        if c:
            j["cta_sent"] = c["message_id"]
    j["step"] = 8'''
PAID_NEW = '''    if not j.get("cta_sent"):
        c = tg("sendMessage", chat_id=chat, text=cta_text(), parse_mode="HTML", disable_web_page_preview=True)
        if c:
            j["cta_sent"] = c["message_id"]
    # --- v11.1: the LAST message of every test is the paid-batches showcase (payment links in buttons)
    if not j.get("paid_msg"):
        try:
            j["paid_msg"] = paid.post_after_test(SELF, chat, job=job, day=day)
        except Exception as e:
            log("paid message failed:", str(e)[:120])
    j["step"] = 8'''

# ---------- result data: English notes + topics ----------
RES_OLD = '''            "note": ("Source: %s · truncation applied on %d option(s) · skipped rows: %d"
                     % (plan.get("src"), plan.get("trunc", 0), len(plan.get("skip_rows") or []))),'''
RES_NEW = '''            "note": ("Source: %s · %d option(s) shortened to fit the platform limit · %d row(s) skipped"
                     % (plan.get("src"), plan.get("trunc", 0), len(plan.get("skip_rows") or []))),'''
RES2_OLD = '''        keys.append({"n": i + 1, "q": q["q"], "opts": q["o"], "ans_idx": int(q["key"]),'''
RES2_NEW = '''        qt = q["q"]
        tp = (q.get("topic") or "").strip()
        if tp:
            tp = tr.translate_safe(tp) if tr.needs_translation(tp) else " ".join(tp.split())
            qt = "[%s] %s" % (tp[:40], qt)
        keys.append({"n": i + 1, "q": qt, "opts": q["o"], "ans_idx": int(q["key"]),'''
CAP_OLD = '''        doc = tg_file(path, chat_id=chat, caption="📄 %s — %s · %dQ scores + answer key"
                      % (plan.get("label") or job.upper(), day_label(day), plan["n"]))'''
CAP_NEW = '''        doc = tg_file(path, chat_id=chat, caption=tr.t("rf_caption", label=plan.get("label") or job.upper(),
                                                        date=day_label(day), n=plan["n"]))'''

# ---------- defer early runs (runner-minute saver) ----------
DEFER_OLD = '''    if ph == "idle":
        return "wait"'''
DEFER_NEW = '''    if ph == "idle":
        return "wait"
    if ph == "warm" and (go_dt(day, job) - istnow()).total_seconds() > DEFER_SECS:
        log("cycle %s: %.0fs to start -> defer (this run only re-arms)" % (
            job, (go_dt(day, job) - istnow()).total_seconds()))
        return "defer"'''

# ---------- desk pass inside the keepwarm agent ----------
AGENT_OLD = '''    st["agent_last"] = istnow().isoformat(timespec="seconds")
    st["agent_issues"] = issues[-10:]
    jsave(st, "agent pass")'''
AGENT_NEW = '''    # v11.1 front desk: student DMs, payments, join requests (never during a live test -> no 409)
    desk = {}
    try:
        SELF = sys.modules[__name__]
        desk = paid.desk_pass(SELF)
        fixed = paid.pending_links(SELF)
        if fixed:
            log("desk: %d pending join link(s) issued" % fixed)
    except Exception as e:
        issues.append("desk pass failed: %s" % str(e)[:120])
        log("desk pass failed:", str(e)[:140])
    st = jload(force=True)
    st["agent_last"] = istnow().isoformat(timespec="seconds")
    st["agent_issues"] = issues[-10:]
    st["desk_last"] = desk
    jsave(st, "agent pass")'''

# ---------- CLI: translate + paid ----------
CLI_OLD = '''    elif cmd == "booksend":'''
CLI_NEW = '''    elif cmd == "translate":
        txt = " ".join(args)
        print("in :", txt)
        print("out:", tr.translate(txt))
        print("stats:", tr.stats())
    elif cmd == "paid":
        sub = args[0] if args else "desk"
        SELF = sys.modules[__name__]
        if sub == "post":
            print("posted message id:", paid.post_after_test(SELF, args[1] if len(args) > 1 else CHAT))
        elif sub == "desk":
            print(json.dumps(paid.desk_pass(SELF), indent=1, default=str))
        elif sub == "pending":
            print("pending links issued:", paid.pending_links(SELF))
        elif sub == "text":
            print(paid.group_text())
        elif sub == "stats":
            st = jload(force=True)
            print(json.dumps(st.get("paid", {}), indent=1, default=str)[:2000])
    elif cmd == "booksend":'''

REPL = [(ANNOUNCE_OLD, ANNOUNCE_NEW), (POLL_OLD, POLL_NEW), (DRAIN_OLD, DRAIN_NEW), (BASE_OLD, BASE_NEW),
        (POLLEND_OLD, POLLEND_NEW), (PAID_OLD, PAID_NEW), (RES_OLD, RES_NEW), (RES2_OLD, RES2_NEW),
        (CAP_OLD, CAP_NEW), (DEFER_OLD, DEFER_NEW), (AGENT_OLD, AGENT_NEW), (CLI_OLD, CLI_NEW)]

missing = []
for old, new in REPL:
    if old not in s:
        missing.append(old.splitlines()[0][:70])
    else:
        s = s.replace(old, new, 1)
if missing:
    print("MISSING ANCHORS:")
    for m in missing:
        print("  -", m)
    sys.exit(1)
open(P, "w", encoding="utf-8").write(s)
print("part 2 ok: countdown/paid/desk/defer (%d blocks)" % len(REPL))
