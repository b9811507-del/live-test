"""6065-format HTML app generator — exact same template used for sheet deliveries."""
import json, re, pathlib, datetime, hashlib

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "template.html"
FILLER = re.compile(r"^(none of these|all of the above|a and b|b and c|a and d|both a and b)\.? *$", re.I)

def fmt(s):
    s = max(0, int(s)); return f"{s // 60:02d}:{s % 60:02d}"

def build_questions(rows):
    """rows = [(page, raw_row)] -> DATA (same keys as delivery files: s/p/t/q/o/k/a/e)."""
    DATA, bad_key = [], []
    for pg, r in rows:
        ans = (r.get("Correct Answer") or "").upper().strip()
        letters = ["A", "B", "C", "D", "E"]
        opts = [(L, r.get(f"Option {L}", "")) for L in letters]
        opts = [(L, t) for L, t in opts if t]
        if ans not in ("", "E"):
            keep = [o for o in opts if not FILLER.fullmatch(o[1].strip())]
            opts = keep if len(keep) >= 3 else opts[:4]
        keys = [L for L, _ in opts]
        if ans not in keys:
            bad_key.append((r.get("Serial No"), ans, keys))
            ans = keys[0] if keys else "A"
        DATA.append({
            "s": r.get("Serial No", ""), "p": pg, "t": r.get("Topic", ""),
            "q": r.get("Question", ""), "o": [t for _, t in opts],
            "k": keys, "a": (keys.index(ans) if ans in keys else 0),
            "e": r.get("Explanation", ""),
        })
    return DATA, bad_key

def render_html(DATA, pages_per, book, author, brand, spb, key, out_path, built=None):
    pages = sorted({d["p"] for d in DATA}) or [1]
    book, brand = book.strip(), brand.strip()
    meta = {"book": book, "author": author, "brand": brand, "pages": pages,
            "pageLabel": (f"Page {pages[0]}" if len(pages) == 1 else f"Page {pages[0]} to {pages[-1]}"),
            "count": len(DATA), "pagesPer": pages_per, "spb": spb,
            "total": len(DATA) * spb, "timerText": fmt(len(DATA) * spb),
            "key": key or re.sub(r"\W+", "_", pathlib.Path(str(out_path)).stem),
            "built": built or datetime.date.today().isoformat()}
    html = TEMPLATE.read_text(encoding="utf-8")
    blob = json.dumps({"meta": meta, "Q": DATA}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", blob, 1)
    from html import escape as _esc
    head = _esc(f"{book} \u2014 {meta['pageLabel']} \u00b7 {meta['count']} MCQs | {brand}")
    html = re.sub(r"<title>.*?</title>", f"<title>{head}</title>", html, count=1, flags=re.S)
    html = re.sub(r'<meta name="description" content="[^"]*">',
                  f'<meta name="description" content="{head} \u2014 textbook-style MCQ practice.">', html, count=1)
    out = pathlib.Path(str(out_path)); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return meta
