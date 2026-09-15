#!/usr/bin/env python3
"""v11.4.5 — the daily HTML becomes the GROUP'S OWN interactive test file format.

Reference read live from the IARI BOOK group (msg 709): "IARI_p621-625_35Q.html" — a single
self-contained app driven by `var DB = {meta, Q[]}` (30 s/question timer, question palette, test
mode, score + accuracy, per-question explanation, localStorage resume). Template extracted verbatim
to engine/paper_template.html; here we make the engine fill it with the day's paper.
"""
import io

E = "engine/engine.py"
s = io.open(E, encoding="utf-8").read()
n0 = len(s)

# ---------------------------------------------------------------- config + paper builder
old = '''POLL_SECONDS = 30                # open_period + drain window'''
new = '''POLL_SECONDS = 30                # open_period + drain window
PAPER_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_template.html")
PAPER_BRAND = os.environ.get("PAPER_BRAND", "Agri Learning Point")      # matches the IARI group files
PAPER_AUTHOR = os.environ.get("PAPER_AUTHOR", "By SatyamSir")'''
assert old in s, "POLL_SECONDS anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- paper_data / paper_html
old = '''def short_label(label):'''
new = '''def paper_data(job, day, plan):
    """The group's file format: var DB = {meta:{book,pages,pageLabel,pagesPer,count,spb,total,
    timerText,key,built,author,brand}, Q:[{s,p,t,q,o,k,a,e}]} — same shape as the live book files."""
    cfg = JOBS[job]
    Q, pages = [], []
    for i, q in enumerate(plan["questions"]):
        pg = _page_num(q.get("page") or "")
        if pg and pg not in pages:
            pages.append(pg)
        opts = [str(o) for o in q["o"]]
        Q.append({"s": str(q.get("serial") or (i + 1)), "p": pg, "t": (q.get("topic") or "").strip() or "General",
                  "q": q["q"], "o": opts, "k": [chr(65 + j) for j in range(len(opts))],
                  "a": int(q["key"]), "e": " ".join(str(q.get("expl") or "").split())})
    pages = sorted(pages)
    if pages and pages == list(range(pages[0], pages[-1] + 1)):
        ptext, plabel = "%s-%s" % (pages[0], pages[-1]), "Page %d to %d" % (pages[0], pages[-1])
    elif pages:
        ptext, plabel = ", ".join(str(p) for p in pages), "Pages %s" % ", ".join(str(p) for p in pages)
    else:                                            # AFO: mongo set, no book pages
        ptext = plabel = "Full-length set %s" % (plan.get("set_no") or "")
        ptext, plabel = ptext.strip(), ptext.strip()
    label = plan.get("label") or job.upper()
    book = "%s — Pages %s" % (label, ptext) if pages else "%s — %s" % (label, plabel)
    per = {}
    for q in Q:
        per[str(q["p"])] = per.get(str(q["p"]), 0) + 1
    total = len(Q)
    if job in ("malwa", "iari"):
        try:
            total = len(sheet_rows(JOBS[job]["sid"] if job == "iari" else plan.get("src"))) or len(Q)
        except Exception:
            total = len(Q)
    spb = int(POLL_SECONDS)
    secs = len(Q) * spb
    pslug = re.sub(r"[^A-Za-z0-9]+", "-", ptext).strip("-") or "all"
    return {"meta": {"book": book, "author": PAPER_AUTHOR, "brand": PAPER_BRAND, "pages": pages,
                     "pageLabel": plabel, "count": len(Q), "pagesPer": per, "spb": spb, "total": total,
                     "timerText": "%02d:%02d" % (secs // 60, secs % 60),
                     "key": "daily_%s_%s_p%s" % (job, day, pslug), "built": day},
            "Q": Q}, ptext


def paper_html(job, day, plan, out_dir=None, path=None):
    """Render the day's paper in the group's interactive format. Returns (path, pages_text)."""
    db, ptext = paper_data(job, day, plan)
    meta = db["meta"]
    title = "%s — %s · %d MCQs | %s" % (meta["book"], meta["pageLabel"], meta["count"], meta["brand"])
    desc = title + " — textbook-style MCQ practice."
    tpl = io.open(PAPER_TEMPLATE, encoding="utf-8").read()
    js = json.dumps(db, ensure_ascii=False).replace("</", "<\\\\/")
    out = (tpl.replace("__DB_JSON__", js).replace("__TITLE__", esc(title)).replace("__DESC__", esc(desc)))
    if not path:
        slug = re.sub(r"[^A-Z0-9]+", "_", (plan.get("label") or job).upper()).strip("_")
        short = re.sub(r"_BOOK_MCQ.*$|_MAINS.*$", "", slug) or slug
        pslug = re.sub(r"[^A-Za-z0-9]+", "-", ptext).strip("-") or "all"
        path = os.path.join(out_dir or OUTDIR, "%s_p%s_%dQ_%s.html" % (short, pslug, meta["count"], day))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    io.open(path, "w", encoding="utf-8").write(out)
    log("paper html %s: %d Q, pages %s, %d KB -> %s" % (job, meta["count"], ptext, len(out) // 1024,
                                                        os.path.basename(path)))
    return path, ptext


def short_label(label):'''
assert old in s, "short_label anchor not found"
s = s.replace(old, new, 1)

# ---------------------------------------------------------------- main flow: send the paper app
old = '''        slug = re.sub(r"[^A-Z0-9]+", "_", (plan.get("label") or job).upper()).strip("_")
        pages_txt = paper_pages_text(job, plan)
        pslug = re.sub(r"[^A-Za-z0-9]+", "-", pages_txt).strip("-") or "all"
        # v11.4.4: book-file naming -> IARI_BOOK_MCQ_2026_2026-09-16_p2-4-5_35Q.html
        path = os.path.join(OUTDIR, "%s_%s_p%s_%dQ.html" % (slug, day, pslug, plan["n"]))
        builder.render_html(result_data(day, job, plan, rows, ans), 0, plan.get("label") or job.upper(),
                            "AGRI QUIZ WORLD", "@Arunkatyanquiz_bot", LB_ROWS, True, path)'''
new = '''        # v11.4.5: the group's own interactive test-file format (same app as the book files:
        # 30 s/question timer, palette, test mode, score + explanation), named <SHORT>_p<pages>_<N>Q_<date>.html
        path, pages_txt = paper_html(job, day, plan)'''
assert old in s, "file send anchor not found"
s = s.replace(old, new, 1)
io.open(E, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- booksend uses the same app
b = io.open(E, encoding="utf-8").read()
old = '''        DATA = {"title": "%s · BOOK MCQ" % job.upper(), "label": "%s (pages %d-%d)" % (job.upper(), chunk[0], chunk[-1]),
                "nq": len(qs), "pages": "Pages %d-%d" % (chunk[0], chunk[-1]),
                "rows": [], "key": [{"n": n + 1, "q": q["q"], "opts": q["opts"], "ans_idx": q["key"],
                                     "ans": "%s. %s" % (chr(65 + q["key"]), q["opts"][q["key"]])}
                                    for n, q in enumerate(qs)]}
        path = os.path.join(OUTDIR, "booksend/%s_%d-%d.html" % (job, chunk[0], chunk[-1]))
        builder.render_html(DATA, step, job.upper(), "AGRI QUIZ WORLD", "@MCQBYBOOK_bot", 48, True, path)
        cap = "📚 %s — pages %d-%d (%d Q) · answers included 📄" % (job.upper(), chunk[0], chunk[-1], len(qs))'''
new = '''        # v11.4.5: book files use the same interactive app as the group's existing 215 files
        bplan = {"label": JOBS.get(job, {}).get("label") or job.upper(), "set_no": None,
                 "questions": [{"serial": q.get("serial"), "page": q.get("page"), "topic": q.get("topic"),
                                "q": q["q"], "o": q["opts"], "key": q["key"], "expl": q.get("expl")}
                               for q in qs]}
        path, _pt = paper_html(job, str(chunk[0]), bplan, path=os.path.join(
            OUTDIR, "booksend/%s_p%d-%d_%dQ.html" % (job, chunk[0], chunk[-1], len(qs))))
        cap = ("📗 %s · Pages %d-%d · %d Q · File %d/%d"
               % (bplan["label"], chunk[0], chunk[-1], len(qs),
                  i // step + 1, len(range(0, len(pages), step))))'''
assert old in b, "booksend data anchor not found"
b = b.replace(old, new, 1)
io.open(E, "w", encoding="utf-8").write(b)

# ---------------------------------------------------------------- caption
R = "engine/translator.py"
t = io.open(R, encoding="utf-8").read()
old = '''    "rf_caption": ("📄 <b>%(label)s</b> — pages %(pages)s (%(n)s questions) · answers & explanations "
                   "in the file · %(date)s"),'''
new = '''    "rf_caption": ("📗 <b>%(label)s</b> · Pages %(pages)s · %(n)s Q · daily test %(date)s — "
                   "open & attempt with timer, answers + explanations inside 📄"),'''
assert old in t, "rf_caption anchor not found"
t = t.replace(old, new, 1)
io.open(R, "w", encoding="utf-8").write(t)
print("v11.4.5 applied (%d -> %d chars)" % (n0, len(io.open(E, encoding='utf-8').read())))
