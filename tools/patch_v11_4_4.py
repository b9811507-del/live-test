#!/usr/bin/env python3
"""v11.4.4 — the result file is now the day's TEST PAPER, in the same format as the book files
already delivered to the IARI group (e.g. B125_p621-625_35Q.html):

  * header = brand line, book name, "(pages …)", date · time · N questions · scoring
  * NO score board (the leaderboard + top 3 already went to the group)
  * "Answer key" list + "Question-wise" block: every question, all options, the correct one ticked,
    plus the sheet's explanation, so a student who missed the live test can still take it
  * file name carries the pages + question count:  IARI_BOOK_MCQ_2026_2026-09-16_p2-4-5_35Q.html
  * only the most recent test is ever rendered (one file per test run, journaled)
"""
import io

# ------------------------------------------------------------------ builder: explanations
B = "engine/builder.py"
s = io.open(B, encoding="utf-8").read()
old = '''.opt.correct{color:#1c7c34;font-weight:600}'''
new = '''.opt.correct{color:#1c7c34;font-weight:600}
.exp{color:#4a5b4c;font-size:13px;margin:2px 0 10px 20px;border-left:3px solid #dfe8df;padding-left:8px}'''
assert old in s, "css anchor not found"
s = s.replace(old, new, 1)
old = '''            parts.append("<div class='%s'><span class='tick'>%s</span>%s. %s</div>" % (
                cls, tick, chr(65 + idx), _esc(o)))
    return "".join(parts)'''
new = '''            parts.append("<div class='%s'><span class='tick'>%s</span>%s. %s</div>" % (
                cls, tick, chr(65 + idx), _esc(o)))
        if k.get("expl"):
            parts.append("<div class='exp'>&#128214; %s</div>" % _esc(k["expl"]))
    return "".join(parts)'''
assert old in s, "key_detail anchor not found"
s = s.replace(old, new, 1)
io.open(B, "w", encoding="utf-8").write(s)

# ------------------------------------------------------------------ engine: paper-shaped result file
E = "engine/engine.py"
t = io.open(E, encoding="utf-8").read()
old = '''    return {"title": "%s · DAILY TEST RESULT" % (plan.get("label") or job.upper()),
            "label": plan.get("label") or job.upper(), "date": day, "day_label": day_label(day),
            "time": cfg["time_label"], "nq": plan["n"],
            "right": fmt_num(cfg["right"]), "wrong": ("−" + fmt_num(abs(float(cfg["wrong"]))))
            if cfg["wrong"] < 0 else fmt_num(cfg["wrong"]),
            "pages": plan.get("pages") or "", "batch": ("Batch %s" % plan["batch"]) if plan.get("batch") else "",
            "rows": rows, "key": keys,'''
new = '''    # v11.4.4: the file is the day's TEST PAPER in the book-file format (same builder as booksend):
    # no score board (leaderboard + top 3 are already in the group), questions + explanations inside.
    pages_txt = paper_pages_text(job, plan)
    return {"title": "%s · BOOK MCQ" % short_label(plan.get("label") or job.upper()),
            "label": "%s (pages %s)" % (short_label(plan.get("label") or job.upper()), pages_txt),
            "date": day, "day_label": day_label(day),
            "time": cfg["time_label"], "nq": plan["n"],
            "right": fmt_num(cfg["right"]), "wrong": ("−" + fmt_num(abs(float(cfg["wrong"]))))
            if cfg["wrong"] < 0 else fmt_num(cfg["wrong"]),
            "pages": ("Pages %s" % pages_txt), "batch": ("Batch %s" % plan["batch"]) if plan.get("batch") else "",
            "rows": [], "key": keys,'''
assert old in t, "result_data anchor not found"
t = t.replace(old, new, 1)

# key entries carry the sheet explanation + the question's book page
old = '''        keys.append({"n": i + 1, "q": qt, "opts": q["o"], "ans_idx": int(q["key"]),
                     "ans": "%s. %s" % (chr(65 + int(q["key"])), q["o"][int(q["key"])]),
                     "picked": picked})'''
new = '''        keys.append({"n": i + 1, "q": qt, "opts": q["o"], "ans_idx": int(q["key"]),
                     "ans": "%s. %s" % (chr(65 + int(q["key"])), q["o"][int(q["key"])]),
                     "expl": (q.get("expl") or "").strip(), "page": q.get("page") or "",
                     "picked": picked})'''
assert old in t, "keys anchor not found"
t = t.replace(old, new, 1)

# helpers: short book label + paper pages text
old = '''def result_data(day, job, plan, rows, ans):'''
new = '''def short_label(label):
    """Booksend-style short name: "IARI BOOK MCQ 2026" -> "IARI", "MALWA BOOK VOL 1" -> "MALWA VOL 1"."""
    words = [w for w in re.split(r"\\s+", str(label or "").strip()) if w]
    if not words:
        return "BOOK MCQ"
    out = [words[0]]
    if len(words) > 1 and words[1].lower() in ("book", "mains", "selection"):
        if words[1].lower() == "book" and len(words) > 2 and ("vol" in words[2].lower() or words[2].isdigit()):
            out.append(words[2])
        elif words[1].lower() != "book":
            out.append(words[1])
    return " ".join(out).upper()


def paper_pages_text(job, plan):
    """Pages covered by this paper, book-file style: "2, 4, 5" for iari, "1-21" for malwa."""
    if job == "iari":
        pl = pages_sorted(plan.get("pages_list"))
        if pl:
            return ", ".join(str(p) for p in pl)
    txt = str(plan.get("pages") or "")
    txt = re.sub(r"^\\s*(book\\s+)?pages\\s*", "", txt, flags=re.I).strip()
    return txt or "-"


def result_data(day, job, plan, rows, ans):'''
assert old in t, "result_data def anchor not found"
t = t.replace(old, new, 1)

# file name: pages + question count;  caption in book-file style
old = '''        slug = re.sub(r"[^A-Z0-9]+", "_", (plan.get("label") or job).upper()).strip("_")
        path = os.path.join(OUTDIR, "%s_%s_results.html" % (slug, day))
        builder.render_html(result_data(day, job, plan, rows, ans), 0, plan.get("label") or job.upper(),
                            "AGRI QUIZ WORLD", "@Arunkatyanquiz_bot", LB_ROWS, True, path)
        doc = tg_file(path, chat_id=chat, caption=tr.t("rf_caption", label=plan.get("label") or job.upper(),
                                                        date=day_label(day), n=plan["n"]))'''
new = '''        slug = re.sub(r"[^A-Z0-9]+", "_", (plan.get("label") or job).upper()).strip("_")
        pages_txt = paper_pages_text(job, plan)
        pslug = re.sub(r"[^A-Za-z0-9]+", "-", pages_txt).strip("-") or "all"
        # v11.4.4: book-file naming -> IARI_BOOK_MCQ_2026_2026-09-16_p2-4-5_35Q.html
        path = os.path.join(OUTDIR, "%s_%s_p%s_%dQ.html" % (slug, day, pslug, plan["n"]))
        builder.render_html(result_data(day, job, plan, rows, ans), 0, plan.get("label") or job.upper(),
                            "AGRI QUIZ WORLD", "@Arunkatyanquiz_bot", LB_ROWS, True, path)
        doc = tg_file(path, chat_id=chat, caption=tr.t("rf_caption", label=plan.get("label") or job.upper(),
                                                        date=day_label(day), n=plan["n"],
                                                        pages=pages_txt))'''
assert old in t, "file send anchor not found"
t = t.replace(old, new, 1)
io.open(E, "w", encoding="utf-8").write(t)

# ------------------------------------------------------------------ translator: caption
R = "engine/translator.py"
u = io.open(R, encoding="utf-8").read()
old = '''    "rf_caption": "📄 %(label)s — %(date)s · %(n)s questions · scores & answer key",'''
new = '''    "rf_caption": ("📄 <b>%(label)s</b> — pages %(pages)s (%(n)s questions) · answers & explanations "
                   "in the file · %(date)s"),'''
assert old in u, "rf_caption anchor not found"
u = u.replace(old, new, 1)
io.open(R, "w", encoding="utf-8").write(u)
print("v11.4.4 applied: paper-shaped result file (book-file format + explanations)")
