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
sys.path.insert(0, os.path.join(REPO, "engine"))
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
    tmr = [t for t in texts(log) if t.startswith("🗓")]
    reveals = [t for t in texts(log) if t.startswith("✅ <b>Q")]
    toppers = [t for t in texts(log) if "TOP 3" in t]
    paid_msgs = [t for t in texts(log) if "PAID BATCHES" in t]
    ann_id = day_of(st, day, "malwa").get("msg_ann")
    lb = [t for t in texts(log) if "LEADERBOARD" in t]
    cta = [t for t in texts(log) if t.startswith("🌾 Daily schedule")] 
    docs = methods(log, "sendDocument", GROUP)
    edits = [e.get("text") or "" for e in methods(log, "editMessageText", GROUP)]
    cd_vals = [int(m.group(1)) for t in edits for m in [re.search(r"Starting in (\d+)s", t)] if m]
    kb = [e for e in methods(log, "sendMessage", GROUP) if e.get("reply_markup")]
    hinglish = [t for t in texts(log) if any(w in t for w in ("sawal", "dhanyavaad", "Roz ka", "ko pin", "jawab"))]
    last_group_msg = [e for e in log if e.get("chat") == GROUP and e["method"] == "sendMessage"][-1]
    pl = polls(log)
    idx = texts(log)
    ok = (len(ann) == 1 and len(pl) == 20 and all(e.get("open_period") == 30 for e in pl)
          and all(e["question"].startswith("%d/20." % (i + 1)) for i, e in enumerate(pl))
          and len(pin_calls) == 1 and pin_calls[0]["message_id"] == ann_id          # announce is the ONLY pin
          and "Book pages" in ann[0]
          and len(reveals) == 20 and "📖" in reveals[0]                              # reveal + explanation each Q
          and len(lb) == 1 and len(toppers) == 1 and len(docs) == 1 and len(tmr) == 1 and len(cta) == 1
          and idx.index(ann[0]) < idx.index(lb[0]) < idx.index(toppers[0])           # ... < top3
          and idx.index(toppers[0]) < idx.index(cta[0]) and idx.index(tmr[0]) < idx.index(cta[0])
          and len(paid_msgs) == 0 and not kb                                         # paid message OFF
          and cd_vals and max(cd_vals) == 15 and len(cd_vals) >= 4
          and not hinglish and int(j.get("step", 0)) == 8
          and int(day_of(st, day, "iari").get("step", 0)) == 0)
    _ = last_group_msg
    return ok, ("announce=%d polls=%d reveals=%d ticks=%s pins=%d unpins=%d lb=%d top3=%d docs=%d plan=%r "
                "cta=%d paid=%d hinglish=%d step=%s" % (
                    len(ann), len(pl), len(reveals), cd_vals, len(pin_calls), len(unpins), len(lb),
                    len(toppers), len(docs), (tmr[0][:40] if tmr else None), len(cta), len(paid_msgs),
                    len(hinglish), j.get("step")))


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
          and int(day_of(st2, day, "iari").get("step", 0)) == 8 and len(pl2) == 8    # 3 pages = 3+3+2 Q
          and any("IARI BOOK MCQ 2026" in t for t in texts(log2)))
    return ok, ("cycle1: announces=%d polls=%d malwa=%s iari=%s(deferred) | cycle2: iari polls=%d (3 pages) iari.step=%s"
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
    iari_q = [e for e in pl if e["question"].startswith("1/8.")]     # v11.4: 3 pages = 8 Q in fixtures
    cd = [int(mm.group(1)) for e in methods(log, "editMessageText", GROUP)
          for mm in [re.search(r"Starting in (\d+)s", e.get("text") or "")] if mm]
    iann = [t for t in texts(log) if "IARI BOOK MCQ 2026" in t and "poll auto-closes" in t]
    tmr = [t for t in texts(log) if t.startswith("🗓")]
    reveals = [t for t in texts(log) if t.startswith("✅ <b>Q")]
    pin_calls = pins(log)
    unp = methods(log, "unpinChatMessage", GROUP)
    # malwa is still in its late window at 14:30, so malwa + iari both run in this cycle; the newer
    # announce (iari) must end up as the ONLY pinned message -> malwa's announce gets unpinned.
    ok = (int(i.get("step", 0)) == 8 and len(pin_calls) == 2
          and pin_calls[-1]["message_id"] == i.get("msg_ann")
          and [x["message_id"] for x in unp] == [m.get("msg_ann")]
          and len(iann) == 1 and "Book pages: 2, 4, 5" in iann[0]            # 3 pages/day (v11.4)
          and len(tmr) == 2 and any("7, 8, 9" in t for t in tmr)             # tomorrow = next 3 pages
          and int(m.get("step", 0)) == 8 and len(pl) == 28                   # 20 malwa + 8 iari
          and len(reveals) == 28
          and iari_q and (i.get("plan") or {}).get("pages_list") == [2, 4, 5]
          and cd and max(cd) == 15 and max(cd) <= 15
          and len([t for t in texts(log) if "poll auto-closes" in t]) == 2)
    return ok, ("iari.step=%s malwa.step=%s polls=%d reveals=%d iari_pages=%s pins=%s unpinned=%s plan=%d "
                "ticks(max %s)" % (i.get("step"), m.get("step"), len(pl), len(reveals),
                                   (i.get("plan") or {}).get("pages_list"),
                                   [x["message_id"] for x in pin_calls], [x["message_id"] for x in unp],
                                   len(tmr), max(cd) if cd else None))


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
                         "PAID_PRICE_PASHU": "₹151", "PAID_CHAT_PASHU": "-1003947957354"})
    inv = methods(log, "sendInvoice", "9002")
    links = methods(log, "createChatInviteLink", "-1003947957354")
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
          and len(unp) == 1 and unp[0]["message_id"] == 777 and i.get("unpinned") == [777]
          and not [t for t in texts(log) if "PAID BATCHES" in t])
    return ok, "pins=%s unpinned=%s journal.unpinned=%s" % (
        [x["message_id"] for x in pinz], [x["message_id"] for x in unp], i.get("unpinned"))


def case17_paid_catalog(tmp):
    """17. paid message lists all 7 batches with prices and one payment/deep-link button each."""
    day = "2026-09-16"
    env = {"PAID_CHAT_MALWA": "-1003761821341", "PAID_CHAT_IARI": "-1003922097468",
           "PAID_CHAT_NEMRAJ": "-1003853396327", "PAID_CHAT_RKSHARMA": "-1003880198347",
           "PAID_PRICE_IARI": "₹99", "PAID_PRICE_MALWA": "₹151", "PAID_PRICE_NEMRAJ": "₹99",
           "PAID_PRICE_RKSHARMA": "₹99", "PAID_PRICE_AFO": "₹251"}
    p, log, st = mk(tmp, day + "T11:30:00+05:30", args=("paid", "text"), journal=empty_journal(day), env=env)
    txt = p.stdout or ""
    import paid as P
    old = os.environ.copy()
    os.environ.update(env)
    rows = P.group_keyboard(engine_mod).get("inline_keyboard")
    titles = [r[0]["text"] for r in rows]
    ok = (all(t in txt for t in ("IARI BOOK MCQ BATCH", "MALWA BOOK VOL 1+2+HORTICULTURE", "NEMRAJ SUNDA BOOK BATCH",
                                 "RK SHARMA BOOK BATCH", "AFO SELECTION BATCH", "SUGARCANE PREMIUM BATCH",
                                 "PASHUDHAN ADHIKARI BATCH"))
          and "₹99" in txt and "₹151" in txt and "₹251" in txt
          and len(rows) == 8 and any("Enrol ₹251" in t for t in titles))
    os.environ.clear(); os.environ.update(old)
    return ok, "batch titles=%d buttons=%d has_99/151/251=%s" % (
        sum(1 for t in ("IARI", "MALWA", "NEMRAJ", "RK SHARMA", "AFO", "SUGARCANE", "PASHUDHAN") if t in txt),
        len(rows), ("₹99" in txt, "₹151" in txt, "₹251" in txt))


import engine as engine_mod

def case18_razorpay_pay(tmp):
    """18. Razorpay: student taps Pay -> bot creates a payment link -> status=paid -> single-use join link in DM."""
    day = "2026-09-16"
    env = {"RAZORPAY_KEY_ID": "rzp_test_fixture", "RAZORPAY_KEY_SECRET": "fixture_secret",
           "PAID_PRICE_CANE": "₹151", "PAID_CHAT_CANE": "-1003707610763"}
    ups = [{"update_id": 701, "callback_query": {"id": "cb7", "from": {"id": 9007, "first_name": "Kisan"},
                                                 "data": "rzp:cane",
                                                 "message": {"chat": {"id": 9007, "type": "private"}}}}]
    fp = os.path.join(tmp, "upsa.json")
    json.dump(ups, open(fp, "w"))
    p1, log1, st1 = mk(tmp, day + "T10:00:00+05:30", args=("paid", "desk"), journal=empty_journal(day),
                       env=dict(env, ENGINE_FAKE_UPDATES=fp, ENGINE_FAKE_RZP_STATUS="created"))
    links1 = (st1.get("paid") or {}).get("links") or {}
    open_dm = [e for e in methods(log1, "sendMessage", "9007") if "Payment link ready" in (e.get("text") or "")]
    if os.path.exists(os.path.join(tmp, "tg.jsonl")):
        os.remove(os.path.join(tmp, "tg.jsonl"))
    # next desk pass: Razorpay now reports "paid"
    p2, log2, st2 = mk(tmp, day + "T10:03:00+05:30", args=("paid", "desk"),
                       env=dict(env, ENGINE_FAKE_RZP_STATUS="paid"))
    inv2 = methods(log2, "createChatInviteLink", "-1003707610763")
    dm_link = [e for e in methods(log2, "sendMessage", "9007") if "t.me/+FAKE" in (e.get("text") or "")]
    rec = ((st2.get("paid") or {}).get("links") or {}).get("plink_FAKE0001") or {}
    ok = (len(links1) == 1 and bool(open_dm) and rec.get("status") == "paid"
          and len(inv2) == 1 and inv2[0].get("member_limit") == 1 and bool(dm_link)
          and ((st2.get("desk") or {}).get("payments") or {}).get("issued") == 1)
    return ok, "links=%d pay_dm=%s status=%s invite=%d member_limit=%s join_dm=%s" % (
        len(links1), bool(open_dm), rec.get("status"), len(inv2),
        inv2[0].get("member_limit") if inv2 else None, bool(dm_link))


def case19_razorpay_expired(tmp):
    """19. Expired payment link -> student gets a fresh 'pay again' button, nothing else is issued."""
    day = "2026-09-16"
    env = {"RAZORPAY_KEY_ID": "rzp_test_fixture", "RAZORPAY_KEY_SECRET": "fixture_secret",
           "PAID_PRICE_IARI": "₹99", "PAID_CHAT_IARI": "-1003922097468"}
    ups = [{"update_id": 801, "callback_query": {"id": "cb8", "from": {"id": 9008, "first_name": "Sita"},
                                                 "data": "rzp:iari",
                                                 "message": {"chat": {"id": 9008, "type": "private"}}}}]
    fp = os.path.join(tmp, "upsb.json")
    json.dump(ups, open(fp, "w"))
    mk(tmp, day + "T10:00:00+05:30", args=("paid", "desk"), journal=empty_journal(day),
       env=dict(env, ENGINE_FAKE_UPDATES=fp, ENGINE_FAKE_RZP_STATUS="created"))
    if os.path.exists(os.path.join(tmp, "tg.jsonl")):
        os.remove(os.path.join(tmp, "tg.jsonl"))
    p2, log2, st2 = mk(tmp, day + "T10:05:00+05:30", args=("paid", "desk"),
                       env=dict(env, ENGINE_FAKE_RZP_STATUS="expired"))
    exp_dm = [e for e in methods(log2, "sendMessage", "9008") if "expired" in (e.get("text") or "")]
    inv = methods(log2, "createChatInviteLink", "-1003922097468")
    rec = ((st2.get("paid") or {}).get("links") or {}).get("plink_FAKE0001") or {}
    ok = bool(exp_dm) and rec.get("status") == "expired" and len(inv) == 0
    return ok, "expired_dm=%s status=%s invites=%d" % (bool(exp_dm), rec.get("status"), len(inv))


def case20_paid_single(tmp):
    """20. paid showcase is OFF by default; when switched on, two tests on the same day: the second
    paid message deletes the first (no duplicate data)."""
    day = "2026-09-16"
    jr = empty_journal(day)
    jr["paid"] = {"msg_%s_iari" % day: 5000, "day_%s" % day: {"id": 5000, "job": "iari"},
                  "posted_at": "2026-09-16T15:05:00+05:30"}
    jr["days"][day]["malwa"] = {"step": 8, "msg_ann": 1, "lb_sent": True, "congrats_sent": 2,
                                "file_sent": "x", "cta_sent": 3, "tmr_note": 4}
    # 20a: default (no flag) -> no paid message at all
    _reset_afo_day(tmp, day)
    p0, log0, st0 = mk(tmp, day + "T18:00:00+05:30", journal=json.loads(json.dumps(jr)),
                       env={"PAID_PRICE_AFO": "₹251"})
    off_ok = not [e for e in log0 if "PAID BATCHES" in (e.get("text") or "")]
    if os.path.exists(os.path.join(tmp, "tg.jsonl")):
        os.remove(os.path.join(tmp, "tg.jsonl"))
    # 20b: flag on -> supersede + delete behaviour
    _reset_afo_day(tmp, day)
    p, log, st = mk(tmp, day + "T18:00:00+05:30", journal=json.loads(json.dumps(jr)),
                    env={"PAID_PRICE_AFO": "₹251", "PAID_SHOWCASE": "on"})
    dels = methods(log, "deleteMessage", GROUP)
    paid_msgs = [e for e in methods(log, "sendMessage", GROUP) if "PAID BATCHES" in (e.get("text") or "")]
    rec = (st.get("paid") or {}).get("day_%s" % day) or {}
    ok = (off_ok and len(dels) == 1 and dels[0]["message_id"] == 5000 and len(paid_msgs) == 1
          and rec.get("id") == paid_msgs[0]["message_id"] and rec.get("superseded") == 5000
          and (st.get("paid") or {}).get("msg_%s_afo" % day))
    return ok, "off_by_default=%s deleted=%s new_paid=%s journal=%s" % (
        off_ok, [d["message_id"] for d in dels], [m["message_id"] for m in paid_msgs],
        {k: rec.get(k) for k in ("id", "superseded")})


def _fixture_rows(sid):
    import csv as _csv
    rows = list(_csv.reader(open(os.path.join(tmp_fixtures(), sid + ".csv"), encoding="utf-8")))[1:]
    return [r for r in rows if len(r) > 9 and r[3].strip()]


def tmp_fixtures():
    return os.path.join(HERE, "fixtures", "sheets")


def _reset_afo_day(tmp, day):
    """an earlier case consumed this AFO set in the shared tree; put it back so later cases can run
    the 18:00 job too (their own assertions are what matter)."""
    bp = os.path.join(tmp, "tests", "fixtures", "afo_bank.json")
    b = json.load(open(bp, encoding="utf-8"))
    uids = set()
    for d in b["afo_sets"]:
        if d["date"] == day:
            d["status"] = "ready"
            uids = {str(q.get("uid")) for q in (d.get("questions") or [])}
    b["afo_used_q"] = [x for x in (b.get("afo_used_q") or []) if str(x.get("uid")) not in uids]
    json.dump(b, open(bp, "w", encoding="utf-8"), indent=1)


def clear_log(tmp):
    """drop the fake-telegram log so one case never asserts on an earlier case's traffic."""
    p = os.path.join(tmp, "tg.jsonl")
    if os.path.exists(p):
        os.remove(p)


def _fixture_rows(sid):
    import csv as _csv
    rows = list(_csv.reader(open(os.path.join(HERE, "fixtures", "sheets", sid + ".csv"), encoding="utf-8")))[1:]
    return [r for r in rows if len(r) > 9 and r[3].strip()]


def case21_toppers_three(tmp):
    """21. more than 3 players: the message after the leaderboard names exactly the top 3 (medals),
    and each reveal lists who was right / wrong (native-quiz-bot style)."""
    day = "2026-09-17"
    players = [("9101", "Aarav", 0), ("9102", "Bhavna", 0), ("9103", "Chirag", 0),
               ("9104", "Divya", 1), ("9105", "Eshan", 2)]
    fp = os.path.join(tmp, "upd.json")
    json.dump([{"update_id": 500001 + i, "poll_answer": {
        "poll_id": "*", "user": {"id": int(u), "first_name": n, "username": None},
        "option_ids": [o]}} for i, (u, n, o) in enumerate(players)], open(fp, "w"))
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day),
                    env={"ENGINE_FAKE_UPDATES": fp})
    lb = [t for t in texts(log) if "LEADERBOARD" in t and t.startswith("🏆")]
    top = [t for t in texts(log) if "TOP 3" in t]
    rv1 = [t for t in texts(log) if t.startswith("✅ <b>Q1/")]
    fx = _fixture_rows("malwa_vol1")
    key = "ABCDE".index(fx[0][9].strip().upper())
    exp = "✅ <b>Q1/20 · Correct answer: %s) %s</b>" % (chr(65 + key), fx[0][4 + key].strip())
    ranked = [l for l in (top[0].split("\n") if top else []) if l.startswith(("🥇", "🥈", "🥉"))]
    wrong_names = [n for _, n, o in players if o != key]
    right_names = [n for _, n, o in players if o == key]
    board = lb[0] if lb else ""
    ok = (len(lb) == 1 and all(n in board for _, n, _ in players)        # all 5 on the board
          and len(top) == 1 and len(ranked) == 3                         # exactly three toppers
          and all(m in top[0] for m in ("🥇", "🥈", "🥉"))
          and all(n in top[0] for n in right_names) and not any(n in top[0] for n in wrong_names)
          and len(rv1) == 1 and rv1[0].splitlines()[0] == exp            # reveal = sheet answer
          and "fixture explanation" in rv1[0]
          and len([t for t in texts(log) if t.startswith("✅ <b>Q")]) == 20)
    return ok, "players_on_board=%d toppers=%d medals=%s reveal0=%r" % (
        sum(1 for _, n, _ in players if n in board), len(ranked), [l[:14] for l in ranked],
        (rv1[0].splitlines()[0] if rv1 else None))


def case22_exact_start(tmp):
    """22. the announce never goes out early: a run that starts 30 s before the slot still announces
    at 11:00:00 sharp, the 15 s countdown follows, and only then Q1."""
    import datetime as dt
    day = "2026-09-18"
    clear_log(tmp)
    p1, log1, st1 = mk(tmp, day + "T10:59:30+05:30", journal=empty_journal(day))
    j = day_of(st1, day, "malwa")
    ann_at = j.get("announced_at") or ""
    sends = [e for e in log1 if e.get("chat") == GROUP and e["method"] == "sendMessage"]
    first_poll = polls(log1)[0] if polls(log1) else {}
    cd = [int(m.group(1)) for e in methods(log1, "editMessageText", GROUP)
          for m in [re.search(r"Starting in (\d+)s", e.get("text") or "")] if m]
    def _dt(v):
        return dt.datetime.fromisoformat(v) if v else None
    gap = ((_dt(first_poll.get("t")) - _dt(ann_at)).total_seconds()
           if first_poll.get("t") and ann_at else -1)
    ok = (int(j.get("step", 0)) == 8 and ann_at >= day + "T11:00:00"
          and j.get("msg_ann") and sends and sends[0].get("message_id") == j["msg_ann"]
          and len(polls(log1)) == 20 and cd and max(cd) == 15 and gap >= 15)
    return ok, "announced_at=%s first_msg=announce=%s polls=%d countdown(max %s) announce->Q1=%ss" % (
        ann_at, bool(sends) and sends[0].get("message_id") == j.get("msg_ann"), len(polls(log1)),
        max(cd) if cd else None, int(gap))


def case23_reveal_sheet(tmp):
    """23. every reveal carries the sheet's correct option + the sheet's explanation column and the
    names of who answered right / wrong."""
    day = "2026-09-19"
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T14:30:00+05:30",
                    journal=empty_journal(day, malwa={"step": 8}))
    fx = _fixture_rows("iari")
    key = "ABCDE".index(fx[0][9].strip().upper())
    rvs = [t for t in texts(log) if t.startswith("✅ <b>Q")]
    n = len(polls(log))
    first = [t for t in rvs if t.startswith("✅ <b>Q1/")]
    exp = "✅ <b>Q1/%d · Correct answer: %s) %s</b>" % (n, chr(65 + key), fx[0][4 + key].strip())
    ok = (n == 8 and len(rvs) == 8 and len(first) == 1 and first[0].splitlines()[0] == exp
          and "fixture explanation" in first[0]
          and ("👏" in first[0] or "❌" in first[0])                     # right/wrong player names
          and rvs[-1].startswith("✅ <b>Q8/8"))
    return ok, "iari_polls=%d reveals=%d first=%r tail=%r" % (
        n, len(rvs), (first[0].splitlines()[0] if first else None),
        (rvs[-1].splitlines()[0] if rvs else None))


def case24_plan_scope(tmp):
    """24. tomorrow's plan: after 11:00 / 14:30 only the next day's page numbers (malwa + iari);
    after 18:00 the whole next-day test schedule (malwa + iari + AFO set)."""
    day = "2026-09-15"
    _reset_afo_day(tmp, "2026-09-15")
    _reset_afo_day(tmp, "2026-09-16")
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day))
    plans = [t for t in texts(log) if t.startswith("🗓")]
    noon_ok = (len(plans) == 1 and "11:00 AM" in plans[0] and "2:30 PM" in plans[0]
               and "6:00 PM" not in plans[0] and "AFO" not in plans[0])
    clear_log(tmp)
    p2, log2, st2 = mk(tmp, day + "T18:00:00+05:30",
                       journal=empty_journal(day, malwa={"step": 8}, iari={"step": 8}))
    plans2 = [t for t in texts(log2) if t.startswith("🗓")]
    eve = plans2[-1] if plans2 else ""
    eve_ok = len(plans2) == 1 and "🌆 6:00 PM" in eve and "AFO MAINS TEST" in eve and "set" in eve
    return noon_ok and eve_ok, "11:00 plan=%s | 18:00 plan=%s" % (
        (plans[0].replace("\n", " | ")[:80] if plans else None), (eve.replace("\n", " | ")[:110] or None))


def polls_set(log):
    return {e["question"] for e in polls(log)}


def case25_cross_day(tmp):
    """25. the book advances across days: 16-Sep starts fresh, 17-Sep continues where 16-Sep ended
    (iari pages + malwa rows) and no question is repeated."""
    d1, d2 = "2026-09-16", "2026-09-17"
    clear_log(tmp)
    p1, log1, st1 = mk(tmp, d1 + "T11:00:00+05:30", journal=empty_journal(d1))
    clear_log(tmp)
    p2, log2, st2 = mk(tmp, d1 + "T14:30:00+05:30")
    i1, m1 = day_of(st2, d1, "iari"), day_of(st2, d1, "malwa")
    clear_log(tmp)
    p3, log3, st3 = mk(tmp, d2 + "T11:00:00+05:30")
    clear_log(tmp)
    p4, log4, st4 = mk(tmp, d2 + "T14:30:00+05:30")
    i2, m2 = day_of(st4, d2, "iari"), day_of(st4, d2, "malwa")
    p1i, p2i = (i1.get("plan") or {}), (i2.get("plan") or {})
    p1m, p2m = (m1.get("plan") or {}), (m2.get("plan") or {})
    ok = (p1i.get("pages_list") == [2, 4, 5] and p1m.get("row_from") == 0          # fresh Day 1
          and p2i.get("row_from") == p1i.get("bidx_next") and p2i.get("pages_list")
          and p2i.get("pages_list") != p1i.get("pages_list")
          and p2m.get("row_from") == p1m.get("bidx_next") == 20
          and len(polls(log1)) == 20 and len(polls(log2)) == 8 and len(polls(log3)) == 20
          and not (polls_set(log1) & polls_set(log3))                            # malwa no repeat
          and not (polls_set(log2) & polls_set(log4)))                           # iari no repeat
    return ok, ("d1 iari pages=%s rows=%s..%s | d1 malwa rows=%s..%s | d2 iari pages=%s rows=%s..%s "
                "| d2 malwa rows=%s..%s | seed=%s") % (
        p1i.get("pages_list"), p1i.get("row_from"), p1i.get("row_to"), p1m.get("row_from"),
        p1m.get("row_to"), p2i.get("pages_list"), p2i.get("row_from"), p2i.get("row_to"),
        p2m.get("row_from"), p2m.get("row_to"), (i2.get("plan_seed") or {}).get("seeded_from"))


def case26_series_restart(tmp):
    """26. admin order (fresh Day 1 from 16-Sep): with the restart marker set for that day the book
    goes back to the very first page even though the previous day consumed earlier rows."""
    d1, d2 = "2026-09-16", "2026-09-17"
    clear_log(tmp)
    p1, log1, st1 = mk(tmp, d1 + "T11:00:00+05:30", journal=empty_journal(d1))
    clear_log(tmp)
    p2, log2, st2 = mk(tmp, d1 + "T14:30:00+05:30")
    sp = os.path.join(tmp, "state.json")
    st = json.load(open(sp, encoding="utf-8"))
    st["series_reset"] = {"iari": d2, "malwa": d2}
    json.dump(st, open(sp, "w", encoding="utf-8"), indent=1, sort_keys=True)
    clear_log(tmp)
    p3, log3, st3 = mk(tmp, d2 + "T11:00:00+05:30")
    clear_log(tmp)
    p4, log4, st4 = mk(tmp, d2 + "T14:30:00+05:30")
    i2, m2 = day_of(st4, d2, "iari"), day_of(st4, d2, "malwa")
    i1 = day_of(st2, d1, "iari")
    ok = ((i2.get("plan") or {}).get("row_from") == 0 and (m2.get("plan") or {}).get("row_from") == 0
          and (m2.get("plan") or {}).get("vol") == 0
          and (i2.get("plan") or {}).get("pages_list") == (i1.get("plan") or {}).get("pages_list")
          and len(polls(log3)) == 20 and len(polls(log4)) == 8)
    return ok, "restart d2: iari rows=%s..%s pages=%s | malwa rows=%s..%s vol=%s" % (
        (i2.get("plan") or {}).get("row_from"), (i2.get("plan") or {}).get("row_to"),
        (i2.get("plan") or {}).get("pages_list"), (m2.get("plan") or {}).get("row_from"),
        (m2.get("plan") or {}).get("row_to"), (m2.get("plan") or {}).get("vol"))


def case27_paper_file(tmp):
    """27. the file posted after a test is the day's paper in the group's interactive format
    (var DB app: 30 s/Q timer, palette, test mode, score + explanation) — the same shell as the
    IARI group's book files — named <SHORT>_p<pages>_<N>Q_<date>.html and one file per test."""
    import json as _json
    import re as _re
    day = "2026-09-21"
    clear_log(tmp)
    p, log, st = mk(tmp, day + "T11:00:00+05:30", journal=empty_journal(day))
    od = os.path.join(tmp, "out")
    files = sorted(f for f in (os.listdir(od) if os.path.isdir(od) else []) if f.endswith(".html"))
    sent = [e for e in log if e["method"] == "sendDocument" and e.get("chat") == GROUP]
    cap = (sent[0].get("caption") if sent else "") or ""
    doc = open(os.path.join(od, files[0]), encoding="utf-8").read() if files else ""
    db = {}
    try:
        db = _json.loads(_re.search(r"var DB = (\{.*?\});", doc, _re.S).group(1))
    except Exception:
        pass
    meta, qs = (db.get("meta") or {}), (db.get("Q") or [])
    j = day_of(st, day, "malwa")
    ok = (len(files) == 1 and len(sent) == 1
          and _re.match(r"^[A-Z0-9_]+_p[\w,\-]+_%dQ_%s\.html$" % (20, day), files[0])   # name convention
          and j.get("file_sent") == files[0]
          and meta.get("count") == 20 and len(qs) == 20 and meta.get("spb") == 30
          and meta.get("timerText") == "10:00" and meta.get("key", "").startswith("daily_malwa_")
          and all(q.get("e") and q.get("o") and isinstance(q.get("a"), int) for q in qs)
          and "var DB" in doc and "localStorage" in doc and "palette" in doc.lower()
          and "Score board" not in doc
          and "Pages" in cap and "20 Q" in cap)
    return ok, "file=%s meta.count=%s spb=%s timer=%s key=%s expl=%d/%d caption=%r" % (
        (files[0] if files else None), meta.get("count"), meta.get("spb"), meta.get("timerText"),
        meta.get("key"), sum(1 for q in qs if q.get("e")), len(qs), cap[:60])


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
    ("17 paid catalog: all 7 batches + prices + buttons", case17_paid_catalog),
    ("18 Razorpay: pay -> status paid -> one-time join link", case18_razorpay_pay),
    ("19 Razorpay: expired link -> fresh pay button only", case19_razorpay_expired),
    ("20 one paid message per day (supersede + delete)", case20_paid_single),
    ("21 toppers: exactly top 3 + reveal names", case21_toppers_three),
    ("22 exact slot time (nothing before 11:00)", case22_exact_start),
    ("23 reveal = sheet answer + explanation", case23_reveal_sheet),
    ("24 tomorrow-plan scope (pages vs full day)", case24_plan_scope),
    ("25 book advances across days (no repeats)", case25_cross_day),
    ("26 fresh Day 1 restart marker (series_reset)", case26_series_restart),
    ("27 result file = day's test paper (book-file format)", case27_paper_file),
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
