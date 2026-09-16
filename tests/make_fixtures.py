#!/usr/bin/env python3
"""tests/make_fixtures.py — deterministic offline fixtures for the fake-clock battery.
Writes tests/fixtures/sheets/*.csv (same 11-column shape as the real Google Sheets) and
tests/fixtures/afo_bank.json (file-backed 'Mongo' bank: 15-Sep set_no 3, 16-Sep set_no 4, 50 Q each).
Run once before tests/fake_clock.py (the battery calls it if fixtures are missing).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SHEETS = os.path.join(HERE, "fixtures", "sheets")
HEAD = ["Serial No", "Book Page", "Topic", "Question", "Option A", "Option B", "Option C", "Option D",
        "Option E", "Correct Answer", "Explanation"]
KEYS = ["A", "B", "C", "D", "B", "A", "C", "A", "B", "D"]


def write_sheet(name, rows):
    os.makedirs(SHEETS, exist_ok=True)
    path = os.path.join(SHEETS, name + ".csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(HEAD) + "\n")
        for r in rows:
            f.write(",".join('"%s"' % str(c).replace('"', "'") for c in r) + "\n")
    return path


def q_row(serial, page, topic, n, key):
    opts = ["Option %s for %s" % (a, n) for a in "ABCD"] + ["None of these"]
    if key == "E":
        pass
    return [serial, page, topic, "Q%d %s me kya sahi hai? (fixture)" % (n, topic), opts[0], opts[1],
            opts[2], opts[3], opts[4], key, "fixture explanation"]


def malwa_rows(count, topic, page_pairs=True):
    rows = []
    for i in range(count):
        serial = 21 + i
        # real MALWA sheet: ~7 questions per 2-page block -> "1-2", "1-2", …, "3-4", …
        b = i // 7
        page = ("%d-%d" % (2 * b + 1, 2 * b + 2)) if page_pairs else str(1 + i)
        rows.append(q_row(serial, page, topic, serial, KEYS[i % len(KEYS)]))
    return rows


def iari_rows():
    rows, n = [], 1
    for page, cnt in ((2, 3), (4, 3), (5, 2), (7, 4), (8, 3), (9, 2), (10, 2)):
        for _ in range(cnt):
            rows.append(q_row(n, str(page), "Agronomy", n, KEYS[n % len(KEYS)]))
            n += 1
    return rows


def afo_bank():
    sets, used = [], []
    for d, set_no, off in (("2026-09-15", 3, 0), ("2026-09-16", 4, 100)):
        qs = []
        longs = ("A very long option text that definitely exceeds the one hundred character telegram poll "
                 "limit and therefore has to be truncated by the engine layer")
        for i in range(50):
            k = i % 5
            qs.append({"uid": "fixture-%d" % (off + i + 1),
                       "q": "AFO fixture question %d (set %d)" % (i + 1, set_no),
                       "o": [longs if i == 3 else "Choice A %d" % i, "Choice B %d" % i,
                             "Choice C %d" % i, "Choice D %d" % i, "None of these"],
                       "key": k})
        sets.append({"date": d, "status": "ready", "set_no": set_no, "questions": qs,
                     "built_at": "2026-09-12 05:26 UTC", "picked_at": None})
    return {"afo_sets": sets, "afo_used_q": used, "afo_supply": [{"key": "meta", "next_set_no": 4}]}


def main():
    write_sheet("malwa_vol1", malwa_rows(45, "General Agriculture"))
    write_sheet("malwa_vol2", malwa_rows(24, "Plant Breeding"))
    write_sheet("malwa_horti", malwa_rows(10, "Horticulture"))
    write_sheet("iari", iari_rows())
    bank = os.path.join(HERE, "fixtures", "afo_bank.json")
    os.makedirs(os.path.dirname(bank), exist_ok=True)
    json.dump(afo_bank(), open(bank, "w"), indent=0)
    print("fixtures: 4 sheets + afo_bank.json (2 sets x 50 Q)")


if __name__ == "__main__":
    main()
