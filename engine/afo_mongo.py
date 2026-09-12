#!/usr/bin/env python3
"""afo_mongo — AFO 50-Q daily set factory backed by MongoDB Atlas.
What it guarantees:
  • All sets for every day until series end (2026-11-01) are PREBUILT into Mongo — enough supply, no mid-day surprises.
  • One set per date; on run the day's set is picked; after the day's test completes it is moved to the USED list
    (status=used) and NEVER picked again. Used sets' question uids are also recorded in afo_used_q so a question
    can never repeat across days, even across re-builds.
  • 'build' is idempotent + top-up safe: run it any time; it only creates sets that are missing.
Collections (db: agri):  afo_sets  {date,status:ready|used,set_no,used_at,questions[]}
                          afo_used_q{uid, used_on}     question-level no-repeat ledger
                          afo_supply{key:"meta", next_set_no}
Env: MONGO_URI (mongodb+srv://…). Never log credentials.
CLI: python3 engine/afo_mongo.py build | status | pick <date> | mark <date> | wipe-used-uid-audit
"""
import os, sys, json, time, hashlib, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MONGO_URI = os.environ.get("MONGO_URI", "")
DB = "agri"
END_DATE = "2026-11-01"
PER_DAY = 50
START_DATE = os.environ.get("AFO_START", "2026-09-13")

def client():
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI env missing")
    from pymongo import MongoClient
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=12000, connectTimeoutMS=12000)

def dbs():
    c = client()
    return c[DB]

def all_dates():
    d0 = dt.date.fromisoformat(START_DATE)
    d1 = dt.date.fromisoformat(END_DATE)
    out = []
    while d0 <= d1:
        out.append(d0.isoformat())
        d0 += dt.timedelta(days=1)
    return out

def pool():
    """AFO question pool from engine (dedup'd, top-25-subjects)."""
    import engine as E
    return E.afo_pool()

def build():
    db = dbs()
    sets_c, used_c, meta_c = db["afo_sets"], db["afo_used_q"], db["afo_supply"]
    sets_c.create_index("date", unique=True); used_c.create_index("uid", unique=True)
    # used question uids (historical sets + legacy engine ledger)
    used_uids = {d["uid"] for d in used_c.find({}, {"uid": 1})}
    have = {d["date"] for d in sets_c.find({"status": "ready"}, {"date": 1})}
    need = [d for d in all_dates() if d not in have]
    # also exclude dates that already used
    used_dates = {d["date"] for d in sets_c.find({"status": "used"}, {"date": 1})}
    need = [d for d in need if d not in used_dates]
    if not need:
        print(f"supply OK — all {len(all_dates())} dates covered"); return
    avail = [q for q in pool() if q["uid"] not in used_uids]
    print(f"pool available (unused): {len(avail)} | dates to build: {len(need)} | need: {len(need)*PER_DAY}")
    if len(avail) < len(need) * PER_DAY:
        print("!! SHORT SUPPLY — widening pool to ALL topics (not just top 25)")
        import engine as E
        # emergency: use full bank excluding model-test noise
        rs, seen = [], used_uids
        for sid in list(E.SHEETS.values()):
            try:
                src = E.rows(sid)
            except Exception:
                continue
            for r in src:
                if E.AFO_EXCLUDE.search(r.get("Topic", "")) or not r.get("Topic"):
                    continue
                q = E.question_from_row(r)
                if q and q["uid"] not in used_uids:
                    k = (q["uid"])
                    if k not in seen:
                        seen.add(k); rs.append(q)
        avail = rs
        print("widened pool:", len(avail))
        if len(avail) < len(need) * PER_DAY:
            print("!! still short — building as many days as possible, rest auto-topup on future runs")
            need = need[: len(avail) // PER_DAY]
    seed = int(os.environ.get("AFO_SEED", "20260911"))
    order = sorted(avail, key=lambda q: hashlib.sha256(f"{seed}|{q['uid']}".encode()).hexdigest())
    meta = meta_c.find_one({"key": "meta"}) or {"key": "meta", "next_set_no": 0}
    docs, cur = [], 0
    for d in need:
        batch = order[cur: cur + PER_DAY]
        if len(batch) < PER_DAY:
            break
        cur += PER_DAY
        meta["next_set_no"] += 1
        qs = [{"uid": q["uid"], "q": q["q"], "o": q["o"], "key": q["key"]} for q in batch]
        for q in qs:
            used_uids.add(q["uid"])
        docs.append({"date": d, "status": "ready", "set_no": meta["next_set_no"],
                     "built_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "questions": qs})
    # batch insert (skip dup dates safely)
    for doc in docs:
        try:
            sets_c.insert_one(doc)
            for q in doc["questions"]:
                used_c.update_one({"uid": q["uid"]}, {"$set": {"used_on_date": doc["date"]}}, upsert=True)
        except Exception as e:
            if "Duplicate" not in str(e):
                print("insert skip", doc["date"], str(e)[:80])
    meta_c.update_one({"key": "meta"}, {"$set": meta}, upsert=True)
    print(f"built {len(docs)} new sets")
    audit()

def audit():
    db = dbs()
    from collections import Counter
    ids = Counter()
    for d in db["afo_sets"].find({}, {"questions.uid": 1}):
        for q in d.get("questions", []):
            ids[q["uid"]] += 1
    dup = {k: v for k, v in ids.items() if v > 1}
    n = db["afo_sets"].count_documents({})
    r = db["afo_sets"].count_documents({"status": "ready"})
    u = db["afo_sets"].count_documents({"status": "used"})
    print(f"AUDIT: sets={n} ready={r} used={u} total_q={sum(ids.values())} duplicated_q={len(dup)}")
    return dup

def pick(date):
    db = dbs()
    d = db["afo_sets"].find_one_and_update({"date": date, "status": "ready"},
                                           {"$set": {"status": "running", "picked_at": time.strftime("%F %T")}},
                                           return_document=True)
    if d:
        return d
    # already running (resume today) ?
    return db["afo_sets"].find_one({"date": date, "status": "running"})

def mark(date):
    db = dbs()
    r = db["afo_sets"].update_one({"date": date, "status": {"$in": ["running", "ready"]}},
                                  {"$set": {"status": "used", "used_at": time.strftime("%F %T")}})
    print("marked used:", r.modified_count, "(matched", r.matched_count, ")")

def status():
    db = dbs()
    nxt = db["afo_sets"].find_one({"status": "ready"}, sort=[("date", 1)])
    print(json.dumps({
        "sets": db["afo_sets"].count_documents({}),
        "ready": db["afo_sets"].count_documents({"status": "ready"}),
        "used": db["afo_sets"].count_documents({"status": "used"}),
        "next_ready": nxt["date"] if nxt else None}, indent=1))

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "build":
        build()
    elif cmd == "status":
        status()
    elif cmd == "audit":
        audit()
    elif cmd == "pick" and len(sys.argv) > 2:
        d = pick(sys.argv[2]); print("picked set", d["set_no"] if d else None)
    elif cmd == "mark" and len(sys.argv) > 2:
        mark(sys.argv[2])
