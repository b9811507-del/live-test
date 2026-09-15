#!/usr/bin/env python3
"""builder.py — 6065-format self-contained HTML renderer.

Locked signature (SPEC v11 §8):
    render_html(DATA, pages_per, book, author, brand, spb, key, out_path)

Meaning of the arguments (locked here because the old 6065 code is not carried over):
  DATA       dict: title, label, date, day_label, time, nq, right, wrong, pages, batch,
                   rows[{rank,name,uid,score,right,wrong,skip}], key[{n,q,opts,ans_idx,ans,picked[]}],
                   footer, note
  pages_per  pages covered per generated file (book/booksend mode)  -> shown in the header
  book       book title for the header (e.g. "MALWA BOOK VOL 1", "IARI BOOK MCQ 2026")
  author     credit line (default "AGRI QUIZ WORLD")
  brand      brand line printed top and bottom (default "@Arunkatyanquiz_bot")
  spb        sets/blocks per break: rows per score-table block (default 48 == leaderboard block)
  key        True -> render the answer-key section, False -> scores only
  out_path   file to write (html, utf-8)

No external CSS/fonts/images on purpose: the file must open offline on any phone.
"""
import html
import os

CSS = """
*{box-sizing:border-box}
body{margin:0;padding:14px;background:#f4f6f4;color:#152018;
     font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:820px;margin:0 auto}
.card{background:#fff;border:1px solid #d8e2d8;border-radius:14px;padding:14px 16px;margin:0 0 14px}
.brand{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#5c6b5e;
       letter-spacing:.4px;text-transform:uppercase}
h1{font-size:20px;margin:6px 0 2px}
h2{font-size:17px;margin:2px 0 10px}
h3{font-size:15px;margin:16px 0 6px;color:#2f6b3a}
.sub{color:#5c6b5e;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid #dbe4db;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#eef5ee;font-weight:600}
td.n,th.n{text-align:center;white-space:nowrap}
tr.gold td{background:#fff8e1}tr.silver td{background:#f5f5f5}tr.bronze td{background:#fdf1e7}
.pos{color:#1c7c34;font-weight:600}.neg{color:#b3261e;font-weight:600}
.q{margin:10px 0 4px;font-weight:600}
.opt{padding:2px 0 2px 20px;position:relative}
.opt .tick{position:absolute;left:0;font-weight:700}
.opt.correct{color:#1c7c34;font-weight:600}
.opt.you::after{content:" \\1F448 aapka jawab";color:#8a6d00;font-size:12px;font-weight:500}
.skip{color:#8a8f8a;font-size:12px}
.foot{text-align:center;color:#5c6b5e;font-size:12px;padding:6px 0 2px}
.nav{display:flex;justify-content:space-between;gap:8px;font-size:13px;font-weight:600;padding-top:8px;border-top:1px dashed #dbe4db;margin-top:10px}
.nav a{text-decoration:none}
.blk{border-top:2px solid #e5ece5;margin:14px 0 0;padding-top:10px}
@media print{.card{border:0;padding:0;margin:0 0 8px}.nav{display:none}}
"""


def _esc(v):
    return html.escape(str(v if v is not None else ""))


def _fmt_score(v):
    try:
        v = float(v)
    except Exception:
        return _esc(v)
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    return '<span class="%s">%+.1f</span>' % (cls, v)


MEDAL = {1: "gold", 2: "silver", 3: "bronze"}


def scores_block(rows, spb, start_rank=1):
    if not rows:
        return "<p class='sub'>Is test me koi answer nahi aaya. Kal phir milte hain! 👀</p>"
    out = []
    for i in range(0, len(rows), max(1, int(spb))):
        chunk = rows[i:i + max(1, int(spb))]
        t = ["<table><tr><th class='n'>#</th><th>Player</th><th class='n'>Net</th>"
             "<th class='n'>Right</th><th class='n'>Wrong</th><th class='n'>Skip</th></tr>"]
        for r in chunk:
            cls = MEDAL.get(int(r.get("rank", 0)), "")
            t.append(
                "<tr class='%s'><td class='n'>%s</td><td>%s</td><td class='n'>%s</td>"
                "<td class='n'>%s</td><td class='n'>%s</td><td class='n'>%s</td></tr>" % (
                    cls, _esc(r.get("rank")), _esc(r.get("name")), _fmt_score(r.get("score", 0)),
                    _esc(r.get("right", 0)), _esc(r.get("wrong", 0)), _esc(r.get("skip", 0))))
        t.append("</table>")
        out.append("".join(t))
        if i + max(1, int(spb)) < len(rows):
            out.append("<div class='blk'></div><h3>Scores (contd.)</h3>")
    return "".join(out)


def key_block(keys, spb, chunks=True):
    if not keys:
        return ""
    out = []
    for i in range(0, len(keys), max(1, int(spb))):
        chunk = keys[i:i + max(1, int(spb))]
        t = ["<table><tr><th class='n'>Q</th><th>Question</th><th>Correct answer</th></tr>"]
        for k in chunk:
            t.append("<tr><td class='n'>%s</td><td>%s</td><td>%s</td></tr>" % (
                _esc(k.get("n")), _esc(k.get("q")), _esc(k.get("ans"))))
        t.append("</table>")
        out.append("".join(t))
        if chunks and i + max(1, int(spb)) < len(keys):
            out.append("<div class='blk'></div><h3>Answer key (contd.)</h3>")
    return "".join(out)


def key_detail_block(keys):
    """Full question + all options with the right one ticked, plus what the player marked."""
    if not keys:
        return ""
    parts = []
    for k in keys:
        parts.append("<div class='q'>%s. %s</div>" % (_esc(k.get("n")), _esc(k.get("q"))))
        picked = set(int(x) for x in (k.get("picked") or []) if x is not None)
        for idx, o in enumerate(k.get("opts") or []):
            cls = "opt"
            tick = "•"
            if idx == k.get("ans_idx"):
                cls += " correct"
                tick = "&#10004;"
            if idx in picked:
                cls += " you"
            parts.append("<div class='%s'><span class='tick'>%s</span>%s. %s</div>" % (
                cls, tick, chr(65 + idx), _esc(o)))
    return "".join(parts)


def render_html(DATA, pages_per=0, book=None, author=None, brand=None, spb=48, key=True, out_path=None):
    D = dict(DATA or {})
    book = book or D.get("book") or D.get("title") or "DAILY TEST"
    author = author or D.get("author") or "AGRI QUIZ WORLD"
    brand = brand or D.get("brand") or "@Arunkatyanquiz_bot"
    spb = int(spb or 48)
    rows = list(D.get("rows") or [])
    keys = list(D.get("key") or [])
    title = D.get("title") or book
    bits = [_esc(D.get("day_label") or D.get("date") or ""), _esc(D.get("time") or "")]
    if D.get("nq") or keys:
        bits.append(_esc("%s questions" % (D.get("nq") or len(keys))))
    for extra in (D.get("pages"), D.get("batch")):
        if extra:
            bits.append(_esc(extra))
    if D.get("right") is not None:
        bits.append(_esc("+%s / %s" % (D.get("right"), D.get("wrong"))))
    hdr = [
        "<div class='card'><div class='brand'><span>%s</span><span>%s</span></div>"
        "<h1>%s</h1><h2>%s</h2><div class='sub'>%s</div>" % (
            _esc(brand), _esc(author), _esc(title), _esc(D.get("label") or ""), " · ".join(bits))
    ]
    if pages_per:
        hdr.append("<div class='sub'>%s pages per file</div>" % _esc(pages_per))
    hdr.append("</div>")

    body = ["".join(hdr)]
    body.append("<div class='card'><h3>Score board</h3>%s%s</div>" % (
        scores_block(rows, spb),
        ("<div class='sub'>Total players: %s</div>" % len(rows)) if rows else ""))
    if key:
        body.append("<div class='card'><h3>Answer key</h3>%s</div>" % key_block(keys, spb))
        if any(k.get("opts") for k in keys):
            body.append("<div class='card'><h3>Question-wise</h3>%s</div>" % key_detail_block(keys))
    if D.get("note"):
        body.append("<div class='card'><div class='sub'>%s</div></div>" % _esc(D["note"]))
    if D.get("nav"):
        body.append("<div class='card'><div class='nav'>%s</div></div>" % D["nav"])
    body.append("<div class='foot'>%s · %s</div>" % (_esc(brand), _esc(author)))

    out = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           "<title>%s</title><style>%s</style></head><body><div class='wrap'>%s</div></body></html>"
           % (_esc(title), CSS, "".join(body)))
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(out)
    return out_path or out


if __name__ == "__main__":
    demo = {"title": "SMOKE TEST", "label": "MALWA BOOK VOL 1", "day_label": "15 September 2026",
            "time": "11:00 AM IST", "nq": 2, "right": 1.0, "wrong": -0.25, "pages": "Pages 1-2",
            "rows": [{"rank": 1, "name": "Ravi", "score": 1.75, "right": 2, "wrong": 1, "skip": 0}],
            "key": [{"n": 1, "q": "Demo Q?", "opts": ["A", "B"], "ans_idx": 0, "ans": "A", "picked": [0]}]}
    print(render_html(demo, 0, "MALWA BOOK VOL 1", "AGRI QUIZ WORLD", "@Arunkatyanquiz_bot", 48, True,
                      "/tmp/_builder_smoke.html") and "wrote /tmp/_builder_smoke.html")
