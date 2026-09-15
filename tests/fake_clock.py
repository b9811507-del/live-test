#!/usr/bin/env python3
"""tests/fake_clock.py — v11 verification battery (SPEC §9).

Injects a fake clock (ENGINE_NOW + ENGINE_FAKE_SPEED) and runs the REAL engine offline
(ENGINE_FAKE=1 => no Telegram / no Mongo / no Google Sheets network). Every "telegram" call is
recorded to a jsonl file, so we can assert exactly what would have gone to the group.

Cases: 10 locked matrix cases + 2 extra safety cases (rights-blocked, booksend smoke).
Run:  python3 tests/fake_clock.py            (prints PASS/FAIL per case + a summary)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GROUP = "-1003784795446"
ADMIN = "-1009999999"


# --------------------------------------------------------------------------- harness
def build_tree(tmp, journal, env_extra=None):
    for d in ("engine", "agents", "tests/fixtures"):
        src = os.path.join(REPO, d)
        dst = os.path.join(tmp, d)
        if os.path.exists(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    st = os.path.join(tmp, "state.json")
    json.dump(journal, open(st, "w"), indent=0, sort_keys=True)


def run(tmp, args, now, env_extra=None, speed="900"):
    env = dict(os.environ)
    env.update({
        "ENGINE_FAKE": "1", "ENGINE_NOW": now, "ENGINE_FAKE_SPEED": speed,
        "ENGINE_FAKE_LOG": os.path.join(tmp, "tg.jsonl"),
        "ENGINE_FAKE_MEMBER": "administrator",
        "ENGINE_FAKE_SHEETS": os.path.join(tmp, "tests", "fixtures", "sheets"),
        "EXAM_TG_TOKEN": "fake-token", "CHAT_ID": GROUP, "ADMIN_CHAT": ADMIN,
        "GITHUB_REPOSITORY": "b9811507-del/live-test",
    })
    env.pop("GITHUB_TOKEN", None)
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, os.path.join(tmp, "engine", "engine.py")] + list(args),
                       capture_output=True, text=True, env=env, cwd=tmp, timeout=300)
    log = []
    lp = os.path.join(tmp, "tg.jsonl")
    if os.path.exists(lp):
        log = [json.loads(l) for l in open(lp, encoding="utf-8") if l.strip()]
    state = json.load(open(os.path.join(tmp, "state.json"), encoding="utf-8"))
    return p, log, state


def mk(tmp, now, args=("slotchain",), journal=None, env=None):
    if journal is not None:
        json.dump(journal, open(os.path.join(tmp, "state.json"), "w"), indent=0, sort_keys=True)
    return run(tmp, args, now, env)


def methods(log, method, chat=None):
    return [e for e in log if e["method"] == method and (chat is None or e.get("chat") == chat)]


def texts(log, method="sendMessage", chat=GROUP):
    return [e.get("text") or "" for e in methods(log, method, chat)]


def polls(log):
    return methods(log, "sendPoll", GROUP)


def pins(log, chat=GROUP):
    return methods(log, "pinChatMessage", chat)


def day_of(state, day, job):
    return ((state.get("days") or {}).get(day) or {}).get(job) or {}


def empty_journal(day, **jobs):
    d = {}
    for j in ("malwa", "iari", "afo"):
        d[j] = dict(jobs.get(j) or {"step": 0, "qidx": 0, "ans": {}, "names": {}})
    return {"version": "v11", "days": {day: d}, "afo18": {}, "booksend": {}}


# --------------------------------------------------------------------------- cases
def case1_idle(tmp):
    """1. idle pre-window: nothing in the window -> zero group traffic, journal untouched."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T09:30:00+05:30", journal=empty_journal(day))
    ok = (not methods(log, "sendMessage", GROUP) and not polls(log)
          and all(int(day_of(st, day, j).get("step", 0)) == 0 for j in ("malwa", "iari", "afo"))
          and p.returncode == 0)
    return ok, "group posts=%d polls=%d steps=%s rc=%d" % (len(methods(log, "sendMessage", GROUP)),
                                                           len(polls(log)),
                                                           [day_of(st, day, j).get("step") for j in
                                                            ("malwa", "iari", "afo")], p.returncode)


def case2_warm(tmp):
    """2. warm window: announce (2 min before) -> 15s countdown -> 20 polls -> LB -> file -> CTA -> PAID message last."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T10:57:00+05:30", journal=empty_journal(day))
    j = day_of(st, day, "malwa")
    ann = [t for t in texts(log) if "poll auto-closes" in t]
    pin_calls = pins(log)
    unpins = methods(log, "unpinChatMessage", GROUP)
    tmr = [t for t in texts(log) if t.startswith("📖 Tomorrow")]
    ann_id = day_of(st, day, "malwa").get("msg_ann")
    lb = [t for t in texts(log) if "LEADERBOARD" in t]
    cta = [t for t in texts(log) if t.startswith("🌾 Daily schedule")] 
    docs = methods(log, "sendDocument", GROUP)
    edits = [e.get("text") or "" for e in methods(log, "editMessageText", GROUP)]
    cd_vals = [int(m.group(1)) for t in edits for m in [re.search(r"Starting in (\d+)s", t)] if m]
    paid_msgs = [t for t in texts(log) if "PAID BATCHES" in t]
    kb = [e for e in methods(log, "sendMessage", GROUP) if e.get("reply_markup")]
    hinglish = [t for t in texts(log) if any(w in t for w in ("sawal", "dhanyavaad", "Roz ka", "ko pin", "jawab"))]
    last_group_msg = [e for e in log if e.get("chat") == GROUP and e["method"] == "sendMessage"][-1]
    pl = polls(log)
    ok = (len(ann) == 1 and len(pl) == 20 and all(e.get("open_period") == 30 for e in pl)
          and all(e["question"].startswith("%d/20." % (i + 1)) for i, e in enumerate(pl))
          and len(pin_calls) == 1 and pin_calls[0]["message_id"] == ann_id          # announce is the ONLY pin
          and "Book pages" in ann[0] and len(tmr) == 1 and "Tomorrow" in tmr[0]      # pages line + tomorrow note
          and lb and texts(log).index(ann[0]) < texts(log).index(lb[0]) < texts(log).index(tmr[0])
          and len(lb) == 1 and len(docs) == 1 and len(cta) == 1
          and cd_vals and max(cd_vals) == 15 and len(cd_vals) >= 4          # v11.1: single 15s countdown
          and len(paid_msgs) == 1 and "PAID BATCHES" in (last_group_msg.get("text") or "")  # paid = LAST
          and kb and len(kb[-1]["reply_markup"]["inline_keyboard"]) >= 4
          and not hinglish and int(j.get("step", 0)) == 8
          and int(day_of(st, day, "iari").get("step", 0)) == 0)
    return ok, ("announce=%d polls=%d ticks=%s pins=%d(only announce=%s) unpins=%d lb=%d tomorrow=%r docs=%d "
                "cta=%d paid_last=%s buttons=%d hinglish=%d step=%s" % (
                    len(ann), len(pl), cd_vals, len(pin_calls),
                    bool(pin_calls) and pin_calls[0]["message_id"] == ann_id, len(unpins), len(lb),
                    (tmr[0][:42] if tmr else None), len(docs), len(cta),
                    "PAID BATCHES" in (last_group_msg.get("text") or ""),
                    len(kb[-1]["reply_markup"]["inline_keyboard"]) if kb else 0, len(hinglish), j.get("step")))


def case3_overlap(tmp):
    """3. multi-window: malwa (late) runs at 14:00; iari defers (30 min to go) and runs when the chain returns."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T14:00:00+05:30", journal=empty_journal(day))
    ann1 = [t for t in texts(log) if "poll auto-closes" in t]
    pl1, m1, i1 = polls(log), day_of(st, day, "malwa").get("step"), day_of(st, day, "iari").get("step")
    json.dump(st, open(os.path.join(tmp, "state.json"), "w"), indent=0, sort_keys=True)
    if os.path.exists(os.path.join(tmp, "tg.jsonl")):
        os.remove(os.path.join(tmp, "tg.jsonl"))
    p2, log2, st2 = run(tmp, ("slotchain",), day + "T14:28:30+05:30")
    pl2 = polls(log2)
    ok = (len(ann1) == 1 and len(pl1) == 20 and m1 == 8 and i1 == 0 and "defer" in (p.stdout + p.stderr)
          and int(day_of(st2, day, "iari").get("step", 0)) == 8 and len(pl2) == 15
          and any("IARI BOOK MCQ 2026" in t for t in texts(log2)))
    return ok, ("cycle1: announces=%d polls=%d malwa=%s iari=%s(deferred) | cycle2: iari polls=%d iari.step=%s"
                % (len(ann1), len(pl1), m1, i1, len(pl2), day_of(st2, day, "iari").get("step")))


def case4_missed(tmp):
    """4. missed after go+4h: all three sealed missed, ZERO group messages, admin DMs only."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T22:31:00+05:30", journal=empty_journal(day))
    sealed = [day_of(st, day, j).get("missed") for j in ("malwa", "iari", "afo")]
    gp = [e for e in log if e.get("chat") == GROUP and e["method"] in ("sendMessage", "sendPoll", "sendDocument")]
    ad = methods(log, "sendMessage", ADMIN)
    ok = (all(sealed) and len(gp) == 0 and len(ad) == 3
          and all(int(day_of(st, day, j).get("step", 0)) == 8 for j in ("malwa", "iari", "afo")))
    return ok, "sealed=%s group_msgs=%d admin_dms=%d" % (sealed, len(gp), len(ad))


def case5_resume(tmp):
    """5. resume mid-polls: no prebuild, no re-announce, polls continue at Q10, scores kept."""
    day = "2026-09-16"
    tmp_j = empty_journal(day)
    json.dump(tmp_j, open(os.path.join(tmp, "state.json"), "w"), indent=0, sort_keys=True)
    p1, l1, st1 = run(tmp, ("prebuild", "malwa"), day + "T10:00:00+05:30")
    plan = day_of(st1, day, "malwa").get("plan") or {}
    pre_built_at = plan.get("built_at")
    j = day_of(st1, day, "malwa")
    j.update({"step": 2, "qidx": 9, "sent_i": 9, "msg_ann": 777,
              "ans": {"0": {"9001": 0}, "1": {"9002": 1}}, "names": {"9001": "TestAlpha", "9002": "TestBeta"}})
    st1["days"][day]["malwa"] = j
    open(os.path.join(tmp, "state.json"), "w").write(json.dumps(st1, indent=0, sort_keys=True))
    if os.path.exists(os.path.join(tmp, "tg.jsonl")):
        os.remove(os.path.join(tmp, "tg.jsonl"))
    p2, log, st2 = run(tmp, ("slotchain",), day + "T11:05:00+05:30")
    ann = [t for t in texts(log) if "ek answer, poll auto-close" in t]
    pl = polls(log)
    j2 = day_of(st2, day, "malwa")
    ok = (len(ann) == 0 and len(pl) == 10 and pl and pl[0]["question"].startswith("11/20.")
          and (j2.get("plan") or {}).get("built_at") == pre_built_at and int(j2.get("step", 0)) == 8
          and len(methods(log, "sendDocument", GROUP)) == 1)
    return ok, ("re-announce=%d polls=%d first_q=%r plan_rebuilt=%s step=%s"
                % (len(ann), len(pl), pl[0]["question"][:14] if pl else None,
                   (j2.get("plan") or {}).get("built_at") != pre_built_at, j2.get("step")))


def case6_done(tmp):
    """6. step>=8: a finished job is never re-run, no traffic at all."""
    day = "2026-09-16"
    jr = empty_journal(day, malwa={"step": 8, "qidx": 20, "done_at": "2026-09-16T11:12:00+05:30"})
    p, log, st = mk(tmp, day + "T11:20:00+05:30", journal=jr)
    ok = (not methods(log, "sendMessage", GROUP) and not polls(log)
          and int(day_of(st, day, "malwa").get("step", 0)) == 8
          and int(day_of(st, day, "iari").get("step", 0)) == 0)
    return ok, "group posts=%d polls=%d malwa.step=%s" % (len(methods(log, "sendMessage", GROUP)),
                                                          len(polls(log)), day_of(st, day, "malwa").get("step"))


def case7_afo_closed(tmp):
    """7. afo after last_day (2026-11-01): sealed closed=schedule_end, nothing posted."""
    day = "2026-11-02"
    jr = empty_journal(day, malwa={"step": 8}, iari={"step": 8})
    p, log, st = mk(tmp, day + "T18:05:00+05:30", journal=jr)
    a = day_of(st, day, "afo")
    ok = (a.get("closed") == "schedule_end" and int(a.get("step", 0)) == 8
          and not methods(log, "sendMessage", GROUP) and not polls(log))
    return ok, "afo.closed=%s step=%s group_msgs=%d" % (a.get("closed"), a.get("step"),
                                                        len(methods(log, "sendMessage", GROUP)))


def case8_error_isolated(tmp):
    """8. error in one job is isolated: malwa fails, iari still runs to completion (same cycle)."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T14:29:00+05:30", journal=empty_journal(day),
                    env={"ENGINE_FAKE_FAIL": "malwa"})
    m, i = day_of(st, day, "malwa"), day_of(st, day, "iari")
    ok = (m.get("last_error") and int(m.get("step", 0)) == 0 and int(i.get("step", 0)) == 8
          and len([t for t in texts(log) if "poll auto-closes" in t]) == 1   # only iari announced
          and p.returncode == 0)
    return ok, "malwa.last_error=%s malwa.step=%s iari.step=%s rc=%d" % (
        bool(m.get("last_error")), m.get("step"), i.get("step"), p.returncode)


def case9_boundary(tmp):
    """9. exact 14:30:00 IST boundary: iari starts immediately, no countdown edit."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T14:30:00+05:30", journal=empty_journal(day))
    i, m = day_of(st, day, "iari"), day_of(st, day, "malwa")   # 14:30: malwa is still inside its late window
    pl = polls(log)
    iari_q = [e for e in pl if e["question"].startswith("1/15.")]
    cd = [int(mm.group(1)) for e in methods(log, "editMessageText", GROUP)
          for mm in [re.search(r"Starting in (\d+)s", e.get("text") or "")] if mm]
    iann = [t for t in texts(log) if "IARI BOOK MCQ 2026" in t and "poll auto-closes" in t]
    tmr = [t for t in texts(log) if t.startswith("📖 Tomorrow")]
    pin_calls = pins(log)
    unp = methods(log, "unpinChatMessage", GROUP)
    # malwa is still in its late window at 14:30, so malwa + iari both run in this cycle; the newer
    # announce (iari) must end up as the ONLY pinned message -> malwa's announce gets unpinned.
    ok = (int(i.get("step", 0)) == 8 and len(pin_calls) == 2
          and pin_calls[-1]["message_id"] == i.get("msg_ann")
          and [x["message_id"] for x in unp] == [m.get("msg_ann")]
          and len(iann) == 1 and "Book pages: 2, 4, 5, 7, 8" in iann[0]      # iari pages listed exactly
          and len(tmr) == 2 and any("9, 10" in t for t in tmr)              # iari tomorrow = pages 9, 10
          and int(m.get("step", 0)) == 8 and len(pl) == 35
          and iari_q and (i.get("plan") or {}).get("pages_list") == [2, 4, 5, 7, 8]
          and cd and max(cd) == 15 and max(cd) <= 15
          and len([t for t in texts(log) if "poll auto-closes" in t]) == 2)
    return ok, "iari.step=%s malwa.step=%s polls=%d iari_pages=%s pins=%s unpinned=%s tomorrow=%d ticks(max %s)" % (
        i.get("step"), m.get("step"), len(pl), (i.get("plan") or {}).get("pages_list"),
        [x["message_id"] for x in pin_calls], [x["message_id"] for x in unp], len(tmr), max(cd) if cd else None)


def case10_next_day(tmp):
    """10. afo next-day advance: 16-Sep runs set_no 4 (not the stale 15-Sep set) and marks it used."""
    day = "2026-09-16"
    jr = empty_journal(day, malwa={"step": 8}, iari={"step": 8})
    p, log, st = mk(tmp, day + "T18:00:00+05:30", journal=jr)
    a = day_of(st, day, "afo")
    pl = polls(log)
    bank = json.load(open(os.path.join(tmp, "tests", "fixtures", "afo_bank.json"), encoding="utf-8"))
    used = {d["date"]: d["status"] for d in bank["afo_sets"]}
    optlens = [len(o) for e in pl for o in (e.get("options") or [])]
    aann = [t for t in texts(log) if "AFO MAINS TEST" in t and "poll auto-closes" in t]
    a_pins = pins(log)
    ok = (int(a.get("step", 0)) == 8 and (a.get("plan") or {}).get("set_no") == 4 and len(pl) == 50
          and pl[0]["question"].startswith("1/50.") and "set 4" in pl[0]["question"]
          and optlens and max(optlens) <= 100 and (a.get("plan") or {}).get("trunc", 0) >= 1
          and used.get("2026-09-16") == "used" and used.get("2026-09-15") == "ready")
    return ok, "plan.set_no=%s polls=%d trunc=%s max_opt_len=%d pins=%d bank_status=%s" % (
        (a.get("plan") or {}).get("set_no"), len(pl), (a.get("plan") or {}).get("trunc"),
        max(optlens) if optlens else -1, len(a_pins), used)


def case11_blocked(tmp):
    """11. SAFETY: bot not admin -> nothing posted to the group, journal blocked, admin DM."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T14:30:00+05:30", journal=empty_journal(day),
                    env={"ENGINE_FAKE_MEMBER": "member"})
    i, m = day_of(st, day, "iari"), day_of(st, day, "malwa")   # 14:30 -> malwa is in its late window too
    gp = [e for e in log if e.get("chat") == GROUP and e["method"] in ("sendMessage", "sendPoll")]
    ad = methods(log, "sendMessage", ADMIN)
    ok = (len(gp) == 0 and i.get("blocked") and m.get("blocked") and int(i.get("step", 0)) == 0
          and len(ad) == 2 and all("bot ko pin" not in (e.get("text") or "") for e in ad))
    return ok, "group_msgs=%d blocked(iari,malwa)=%s/%s admin_dms=%d" % (
        len(gp), bool(i.get("blocked")), bool(m.get("blocked")), len(ad))


def case12_booksend(tmp):
    """12. booksend smoke (offline): 2 files pinned + INDEX last + nav filled on every file."""
    day = "2026-09-16"
    p, log, st = mk(tmp, day + "T09:00:00+05:30", args=("booksend", "iari", "2-5", "2", "-1003922097468"),
                    journal=empty_journal(day))
    docs = methods(log, "sendDocument", "-1003922097468")
    pin_list = pins(log, "-1003922097468")
    idx = [t for t in texts(log, chat="-1003922097468") if "INDEX" in t]
    navs = [e for e in methods(log, "editMessageCaption", "-1003922097468")]
    ok = (len(docs) == 2 and len(pin_list) == 3 and len(idx) == 1 and len(navs) == 2
          and (st.get("booksend") or {}).get("done") is True)
    return ok, "files=%d pins=%d index=%d nav_edits=%d done=%s" % (
        len(docs), len(pin_list), len(idx), len(navs), (st.get("booksend") or {}).get("done"))


def case13_desk_enrol(tmp):
    """13. enrolment: /start buy_afo -> batch detail -> claim -> single-use join link into the student's chat."""
    day = "2026-09-16"
    ups = [
        {"update_id": 501, "message": {"chat": {"id": 9001, "type": "private"},
                                       "from": {"id": 9001, "first_name": "Ravi"}, "text": "/start buy_afo"}},
        {"update_id": 502, "callback_query": {"id": "cb1", "from": {"id": 9001, "first_name": "Ravi"},
                                              "data": "claim:afo",
                                              "message": {"chat": {"id": 9001, "type": "private"}}}},
    ]
    fp = os.path.join(tmp, "ups.json")
    json.dump(ups, open(fp, "w"))
    p, log, st = mk(tmp, day + "T12:00:00+05:30", args=("paid", "desk"), journal=empty_journal(day),
                    env={"ENGINE_FAKE_UPDATES": fp})
    dms = methods(log, "sendMessage", "9001")
    links = methods(log, "createChatInviteLink", "-1003687531473")
    paid_rec = (((st.get("paid") or {}).get("users") or {}).get("9001") or {}).get("batches", {}).get("afo", {})
    link_dm = [e for e in dms if "t.me/+FAKE" in (e.get("text") or "")]
    ok = (len(dms) >= 3 and len(links) == 1 and links[0].get("member_limit") == 1
          and bool(link_dm) and paid_rec.get("link_status") == "issued")
    return ok, "student DMs=%d invite_links=%d member_limit=%s link_sent=%s entitlement=%s" % (
        len(dms), len(links), links[0].get("member_limit") if links else None, bool(link_dm),
        paid_rec.get("link_status"))


def case14_desk_invoice(tmp):
    """14. Telegram Payments path: invoice -> successful_payment -> automatic join link (no manual step)."""
    day = "2026-09-16"
    ups = [
        {"update_id": 601, "callback_query": {"id": "cb9", "from": {"id": 9002, "first_name": "Sunita"},
                                              "data": "invoice:pashu",
                                              "message": {"chat": {"id": 9002, "type": "private"}}}},
        {"update_id": 602, "message": {"chat": {"id": 9002, "type": "private"},
                                       "from": {"id": 9002, "first_name": "Sunita"},
                                       "successful_payment": {"invoice_payload": "batch:pashu:9002",
                                                              "total_amount": 15100, "currency": "INR"}}},
    ]
    fp = os.path.join(tmp, "ups2.json")
    json.dump(ups, open(fp, "w"))
    p, log, st = mk(tmp, day + "T12:00:00+05:30", args=("paid", "desk"), journal=empty_journal(day),
                    env={"ENGINE_FAKE_UPDATES": fp, "PAY_PROVIDER_TOKEN": "fake-provider-token",
                         "PAID_PRICE_PASHU": "₹151"})
    inv = methods(log, "sendInvoice", "9002")
    links = methods(log, "createChatInviteLink", "-10033947957354")
    link_dm = [e for e in methods(log, "sendMessage", "9002") if "t.me/+FAKE" in (e.get("text") or "")]
    ok = len(inv) == 1 and len(links) == 1 and bool(link_dm)
    return ok, "invoices=%d invite_links=%d link_sent=%s" % (len(inv), len(links), bool(link_dm))


def case15_desk_silent(tmp):
    """15. SAFETY: the desk never polls while a test is live (no 409 with the exam poller)."""
    day = "2026-09-16"
    jr = empty_journal(day)
    jr["days"][day]["malwa"] = {"step": 2, "qidx": 5, "ans": {}, "names": {}, "lock_ts": time.time()}
    p, log, st = mk(tmp, day + "T11:05:00+05:30", args=("paid", "desk"), journal=jr)
    ok = (not methods(log, "getUpdates") and "skipped" in (p.stdout or "") + (p.stderr or ""))
    return ok, "getUpdates calls=%d skipped=%s" % (len(methods(log, "getUpdates")),
                                                   "skipped" in (p.stdout or "") + (p.stderr or ""))


def case16_single_pin(tmp):
    """16. new announce unpins the older one -> exactly ONE pinned message (the current announce)."""
    day = "2026-09-16"
    jr = empty_journal(day)
    jr["days"][day]["malwa"] = {"step": 8, "qidx": 20, "msg_ann": 777, "lb_sent": True,
                                "congrats_sent": 778, "file_sent": "x", "cta_sent": 779}
    p, log, st = mk(tmp, day + "T14:29:00+05:30", journal=jr)          # iari announces
    i = day_of(st, day, "iari")
    unp = methods(log, "unpinChatMessage", GROUP)
    pinz = pins(log)
    ok = (len(pinz) == 1 and pinz[0]["message_id"] == i.get("msg_ann")
          and len(unp) == 1 and unp[0]["message_id"] == 777 and i.get("unpinned") == [777])
    return ok, "pins=%s unpinned=%s journal.unpinned=%s" % (
        [x["message_id"] for x in pinz], [x["message_id"] for x in unp], i.get("unpinned"))


CASES = [
    ("1  idle pre-window", case1_idle),
    ("2  warm window (announce+countdown+20Q)", case2_warm),
    ("3  multi-window overlap (malwa late + iari warm)", case3_overlap),
    ("4  missed after go+4h (sealed, team silent)", case4_missed),
    ("5  resume mid-polls (no prebuild/re-announce)", case5_resume),
    ("6  step>=8 skip", case6_done),
    ("7  afo closed after last_day", case7_afo_closed),
    ("8  error in one job isolated", case8_error_isolated),
    ("9  slot_go exact 14:30:00 IST boundary", case9_boundary),
    ("10 afo next-day advance (set_no 4)", case10_next_day),
    ("11 SAFETY: bot not admin -> blocked, silent group", case11_blocked),
    ("12 SAFETY: booksend smoke (manual job)", case12_booksend),
    ("13 enrolment: claim -> single-use join link in DM", case13_desk_enrol),
    ("14 enrolment: Telegram invoice -> auto join link", case14_desk_invoice),
    ("15 SAFETY: desk silent while a test is live", case15_desk_silent),
    ("16 single pin: new announce unpins the older one", case16_single_pin),
]


def main():
    if not os.path.exists(os.path.join(HERE, "fixtures", "afo_bank.json")):
        subprocess.run([sys.executable, os.path.join(HERE, "make_fixtures.py")], check=True)
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    fails = 0
    for name, fn in CASES:
        if only and not name.startswith(only):
            continue
        tmp = tempfile.mkdtemp(prefix="v11case-")
        try:
            build_tree(tmp, {"version": "v11", "days": {}})
            ok, detail = fn(tmp)
        except Exception as e:
            ok, detail = False, "harness error: %s" % str(e)[:200]
        print("%-52s %s  %s" % (name, "PASS" if ok else "FAIL", detail), flush=True)
        if not ok:
            fails += 1
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nbattery: %d/%d cases passed" % (len(CASES) - fails, len(CASES)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
