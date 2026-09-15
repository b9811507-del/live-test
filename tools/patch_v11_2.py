#!/usr/bin/env python3
"""One-shot patch v11.2 (admin order 2026-09-15):
  1. malwa + iari announce/countdown carry the book page numbers
  2. after their leaderboard -> a short "tomorrow's pages" note
  3. ONLY the announce message is pinned: no congrats pin, no series pin, and older pins of ours
     (incl. the stale 14-Sep announce 29092) are unpinned when a new announce goes up
Run from repo root: python3 tools/patch_v11_2.py
"""
import sys

# ---------------------------------------------------------------- 1. translator strings
P = "engine/translator.py"
s = open(P, encoding="utf-8").read()
s = s.replace('''    "ann_body": "📝 %(n)s questions · 30 seconds each · one answer, poll auto-closes",''',
'''    "ann_body": "📝 %(n)s questions · 30 seconds each · one answer, poll auto-closes",
    "ann_pages": "📖 Book pages: %(pages)s",
    "ann_pages_range": "📖 %(pages)s",
    "tomorrow_note": "📖 Tomorrow (%(date)s): <b>%(label)s</b> — book pages %(pages)s",''')
open(P, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- 2. engine
P = "engine/engine.py"
s = open(P, encoding="utf-8").read()
orig = s

# --- 2a. pages-aware announce + countdown
OLD = '''def announce_text(job, day, plan):
    """4-line announce in professional English (locked shape: title / date+time / questions / scoring)."""
    cfg = JOBS[job]
    return "\\n".join([
        tr.t("ann_title", emoji=cfg["emoji"], label=plan.get("label") or cfg.get("label") or job.upper()),
        tr.t("ann_when", date=day_label(day), time=cfg["time_label"]),
        tr.t("ann_body", n=plan["n"]),
        tr.t("ann_score", right=fmt_num(cfg["right"]),
             wrong=fmt_num(abs(float(cfg["wrong"]))) if cfg["wrong"] < 0 else fmt_num(cfg["wrong"])),
    ])


def countdown_text(job, day, plan, secs):
    cfg = JOBS[job]
    return "\\n".join([
        tr.t("ann_title", emoji=cfg["emoji"], label=plan.get("label") or cfg.get("label") or job.upper()),
        tr.t("ann_when", date=day_label(day), time=cfg["time_label"]),
        tr.t("ann_body", n=plan["n"]).split(" · ")[0] + " · 30 seconds each",
        tr.t("cd_line", n=max(0, int(secs))),
    ])'''
NEW = '''def pages_text(job, plan):
    """Page numbers for the announce (v11.2): iari lists the exact pages, malwa the covered range."""
    if job == "iari" and plan.get("pages_list"):
        return tr.t("ann_pages", pages=", ".join(str(p) for p in plan["pages_list"]))
    if job in ("malwa", "iari") and plan.get("pages"):
        return tr.t("ann_pages_range", pages=str(plan["pages"]).replace("Book pages", "Book pages"))
    return ""


def announce_text(job, day, plan):
    """Announce in professional English: title / date+time / pages (malwa+iari) / questions / scoring."""
    cfg = JOBS[job]
    lines = [tr.t("ann_title", emoji=cfg["emoji"], label=plan.get("label") or cfg.get("label") or job.upper()),
             tr.t("ann_when", date=day_label(day), time=cfg["time_label"])]
    pg = pages_text(job, plan)
    if pg:
        lines.append(pg)
    lines += [tr.t("ann_body", n=plan["n"]),
              tr.t("ann_score", right=fmt_num(cfg["right"]),
                   wrong=fmt_num(abs(float(cfg["wrong"]))) if cfg["wrong"] < 0 else fmt_num(cfg["wrong"]))]
    return "\\n".join(lines)


def countdown_text(job, day, plan, secs):
    cfg = JOBS[job]
    lines = [tr.t("ann_title", emoji=cfg["emoji"], label=plan.get("label") or cfg.get("label") or job.upper()),
             tr.t("ann_when", date=day_label(day), time=cfg["time_label"])]
    pg = pages_text(job, plan)
    if pg:
        lines.append(pg)
    lines += [tr.t("ann_body", n=plan["n"]).split(" · ")[0] + " · 30 seconds each",
              tr.t("cd_line", n=max(0, int(secs)))]
    return "\\n".join(lines)


def tomorrow_pages_note(job, day, st):
    """Short note after the leaderboard: which pages the next test covers (malwa + iari only).
    Read-only preview of the next batch — it never touches the journal, Mongo or the group."""
    if job not in ("malwa", "iari"):
        return None
    j = job_j(st, day, job)
    try:
        if job == "malwa":
            nxt, _, why = plan_malwa(day, {"vol": j.get("vol", 0), "bidx": j.get("bidx", 0)})
            if not nxt:
                return None
            plist = nxt.get("pages_list") or []
            ptext = ", ".join(str(p) for p in plist) if plist else str(nxt.get("pages") or "").replace("Book pages ", "")
        else:
            nxt, _, why = plan_iari(day, {"bidx": j.get("bidx", 0)})
            if not nxt:
                return None
            plist = nxt.get("pages_list") or []
            ptext = ", ".join(str(p) for p in plist) if plist else str(nxt.get("pages") or "")
        if not ptext:
            return None
        label = nxt.get("label")
    except Exception as e:
        log("tomorrow note skipped:", str(e)[:110])
        return None
    tmr = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    return tr.t("tomorrow_note", date=day_label(tmr), label=label, pages=ptext)


def unpin_other_announces(chat, keep_id, st=None):
    """Admin order v11.2: ONLY the announce message stays pinned. When a new announce is pinned,
    every other announce this engine ever posted (journaled msg_ann ids, incl. the stale 14-Sep
    announce 29092) is unpinned. Nothing else is ever pinned by the engine."""
    st = st if st is not None else jload()
    ids = set()
    for d, jobs in (st.get("days") or {}).items():
        for jb, jj in (jobs or {}).items():
            if isinstance(jj, dict) and jj.get("msg_ann"):
                try:
                    ids.add(int(jj["msg_ann"]))
                except Exception:
                    pass
    a = st.get("afo18") or {}
    if isinstance(a, dict) and a.get("msg_ann"):
        try:
            ids.add(int(a["msg_ann"]))
        except Exception:
            pass
    unpinned = []
    for mid in sorted(ids):
        if keep_id and mid == int(keep_id):
            continue
        tg("unpinChatMessage", chat_id=chat, message_id=mid)
        unpinned.append(mid)
    if unpinned:
        log("unpinned older announce(s): %s (kept %s)" % (unpinned, keep_id))
    return unpinned'''
assert OLD in s
s = s.replace(OLD, NEW, 1)

# --- 2b. announce step: unpin older announces right after pinning the new one
OLD = '''            j["pinned_ann"] = bool(p)
            if not p:
                dm_admin(tr.t("adm_pin", job=job.upper()), "pin:" + job, 6 * 3600)
            jsave(st, "%s announce #%s" % (job, j["msg_ann"]))'''
NEW = '''            j["pinned_ann"] = bool(p)
            if not p:
                dm_admin(tr.t("adm_pin", job=job.upper()), "pin:" + job, 6 * 3600)
            # v11.2: keep exactly one pinned message in the group -> the current announce
            try:
                j["unpinned"] = unpin_other_announces(chat, m["message_id"], st)
            except Exception as e:
                log("unpin pass failed:", str(e)[:100])
            jsave(st, "%s announce #%s" % (job, j["msg_ann"]))'''
assert OLD in s
s = s.replace(OLD, NEW, 1)

# --- 2c. tomorrow note after the leaderboard
OLD = '''        j["lb_sent"] = True
        j["step"] = 4
        j["players"] = len(rows)
        j["answered_total"] = sum(len(v) for v in ans.values())
        jsave(st, "%s leaderboard" % job)'''
NEW = '''        j["lb_sent"] = True
        j["step"] = 4
        j["players"] = len(rows)
        j["answered_total"] = sum(len(v) for v in ans.values())
        jsave(st, "%s leaderboard" % job)
        # v11.2: short note right after the leaderboard — what tomorrow's pages will be
        if not j.get("tmr_note") and job in ("malwa", "iari"):
            try:
                note = tomorrow_pages_note(job, day, st)
            except Exception as e:
                note = None
                log("tomorrow note failed:", str(e)[:100])
            if note:
                m2 = tg("sendMessage", chat_id=chat, text=note, parse_mode="HTML",
                        disable_web_page_preview=True)
                if m2:
                    j["tmr_note"] = m2["message_id"]
                    j["tmr_note_text"] = note
                    jsave(st, "%s tomorrow note" % job)
                    log("tomorrow note sent: %s" % note.replace("\\n", " ")[:120])'''
assert OLD in s
s = s.replace(OLD, NEW, 1)

# --- 2d. congratulations: send but never pin
OLD = '''    if not j.get("congrats_sent"):
        c = tg("sendMessage", chat_id=chat, text=congrats_text(job, day, plan, rows), parse_mode="HTML",
               disable_web_page_preview=True)
        if c:
            tg("pinChatMessage", chat_id=chat, message_id=c["message_id"])
            j["congrats_sent"] = c["message_id"]
            jsave(st, "%s congrats" % job)'''
NEW = '''    if not j.get("congrats_sent"):
        c = tg("sendMessage", chat_id=chat, text=congrats_text(job, day, plan, rows), parse_mode="HTML",
               disable_web_page_preview=True)
        if c:
            # v11.2: NOT pinned (only the announce is pinned in this group)
            j["congrats_sent"] = c["message_id"]
            jsave(st, "%s congrats (unpinned by rule)" % job)'''
assert OLD in s
s = s.replace(OLD, NEW, 1)

# --- 2e. series-complete message: send but never pin
OLD = '''            if m:
                tg("pinChatMessage", chat_id=CHAT, message_id=m["message_id"])
                j["series_posted"] = m["message_id"]'''
NEW = '''            if m:
                # v11.2: not pinned (only the announce is pinned)
                j["series_posted"] = m["message_id"]'''
assert OLD in s
s = s.replace(OLD, NEW, 1)

# --- 2f. stricter Hinglish detection (no script -> require 3 markers, avoids false positives)
P2 = "engine/translator.py"
t = open(P2, encoding="utf-8").read()
t = t.replace('''    hits = sum(1 for m in hindi_markers if m in low)
    return hits >= 2''', '''    hits = sum(1 for m in hindi_markers if m in low)
    return hits >= 3          # English exam text must never be rewritten by a false positive''')
open(P2, "w", encoding="utf-8").write(t)

open(P, "w", encoding="utf-8").write(s)
print("v11.2 patch ok: pages in announce, tomorrow note, announce-only pinning")
