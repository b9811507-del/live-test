#!/usr/bin/env python3
"""afo_mongo.py — AFO full-length bank access (MongoDB Atlas, db `agri`).

LOCKED RULES (SPEC v11 §4):
  * collections: afo_sets {date,status:ready|used|running,set_no,questions:[{uid,q,o[5],key}],used_at}
                 afo_used_q {uid, used_on}   <- no-repeat ledger
                 afo_supply  {key:"meta", next_set_no}
  * build/topup = idempotent · NEVER posts to Telegram from here (no TG code in this module at all).
  * one 50-Q set per IST day; draw = pick(date); after a live test -> mark(date).

Subcommands:
  python3 engine/afo_mongo.py status
  python3 engine/afo_mongo.py audit <date>
  python3 engine/afo_mongo.py pick <date>
  python3 engine/afo_mongo.py mark <date>
  python3 engine/afo_mongo.py supply [--from YYYY-MM-DD --to YYYY-MM-DD]   (audit / gap-fill, idempotent)
"""
import datetime as dt
import json
import os
import sys

DB_NAME = "agri"
NQ = 50
MIN_OPTS, MAX_OPTS = 2, 5
POOL_DATES_FROM = "2026-09-13"
POOL_DATES_TO = "2026-11-01"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE_BANK = os.path.join(ROOT, "tests", "fixtures", "afo_bank.json")


class BankError(Exception):
    pass


def istnow():
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)


def _fake():
    return os.environ.get("ENGINE_FAKE", "") == "1" or os.environ.get("ENGINE_FAKE_MONGO", "") == "1"


# --------------------------------------------------------------------------- local fake bank (offline tests)
class _FakeCol:
    def __init__(self, name, bank):
        self.name, self.bank = name, bank

    def _docs(self):
        return self.bank.setdefault(self.name, [])

    def find(self, flt=None, proj=None):
        flt = flt or {}
        return [d for d in self._docs() if all(d.get(k) == v for k, v in flt.items() if not k.startswith("$"))]

    def find_one(self, flt=None, proj=None):
        r = self.find(flt)
        return r[0] if r else None

    def count_documents(self, flt=None):
        return len(self.find(flt or {}))

    def distinct(self, key):
        return sorted({d.get(key) for d in self._docs() if d.get(key) is not None})

    def update_one(self, flt, upd, upsert=False):
        r = self.find(flt)
        if not r:
            if not upsert:
                return
            doc = dict(flt)
            doc.update(upd.get("$set", {}))
            self._docs().append(doc)
            return
        r[0].update(upd.get("$set", {}))

    def insert_one(self, doc):
        if not any(d.get("uid") == doc.get("uid") for d in self._docs()):
            self._docs().append(dict(doc))


class _FakeDB:
    def __init__(self):
        self.file = FAKE_BANK
        self.bank = json.load(open(self.file)) if os.path.exists(self.file) else {}

    def __getattr__(self, item):
        return _FakeCol(item, self.bank)

    def list_collection_names(self):
        return sorted(self.bank.keys())

    def flush(self):
        if os.environ.get("ENGINE_FAKE_READONLY") != "1":
            json.dump(self.bank, open(self.file, "w"), indent=0, sort_keys=True)


def db_handle(uri=None):
    """Return (db, flush_fn). Real pymongo in prod; file-backed fake when ENGINE_FAKE=1."""
    if _fake():
        f = _FakeDB()
        return f, f.flush
    from pymongo import MongoClient
    uri = uri or os.environ.get("MONGO_URI")
    if not uri:
        raise BankError("MONGO_URI missing")
    cl = MongoClient(uri, serverSelectionTimeoutMS=12000, appname="agri-quiz-v11")
    return cl[DB_NAME], (lambda: None)


# --------------------------------------------------------------------------- validation / audit
def q_problems(q, i):
    """HARD problems only — a question with any of these can never be posted.
    Text/option length is NOT hard: the engine truncates (option <=100 chars) and disambiguates
    collisions, so those come back as warnings from q_warnings() instead."""
    p = []
    if not isinstance(q, dict):
        return ["q%d not a dict" % i]
    if not str(q.get("uid") or "").strip():
        p.append("q%d no uid" % i)
    if not str(q.get("q") or "").strip():
        p.append("q%d empty text" % i)
    opts = q.get("o") or []
    if not (MIN_OPTS <= len(opts) <= MAX_OPTS):
        p.append("q%d options=%d" % (i, len(opts)))
    if any(not str(o).strip() for o in opts):
        p.append("q%d empty option" % i)
    k = q.get("key")
    if not isinstance(k, int) or k < 0 or k >= len(opts):
        p.append("q%d bad key=%r" % (i, k))
    tr = [str(o)[:98].rstrip() + "…" if len(str(o)) > 100 else str(o) for o in opts]
    if len(set(tr)) != len(tr):
        # two options collide after truncation; the engine tags them, only a *keyed* collision is fatal
        if tr[k] in [x for j, x in enumerate(tr) if j != k] if isinstance(k, int) and 0 <= k < len(tr) else False:
            p.append("q%d keyed option collides after truncation" % i)
    return p


def q_warnings(q, i):
    w = []
    if len(str(q.get("q") or "")) > 292:
        w.append("q%d question >292 chars (truncated)" % i)
    if any(len(str(o)) > 100 for o in (q.get("o") or [])):
        w.append("q%d option >100 chars (truncated)" % i)
    return w


def uid_index(db):
    """{date: set(uid)} for every set — built once, reused by supply()."""
    idx = {}
    for d in db.afo_sets.find({}, {"date": 1, "questions.uid": 1}):
        idx[d.get("date")] = {str(q.get("uid")) for q in (d.get("questions") or [])}
    return idx


def audit(date, db=None, index=None):
    """Read-only integrity audit of one date. Returns dict(ok, set_no, problems, nq, uids)."""
    db = db if db is not None else db_handle()[0]
    doc = db.afo_sets.find_one({"date": date})
    out = {"date": date, "ok": False, "set_no": None, "nq": 0, "problems": [], "warns": []}
    if not doc:
        out["problems"].append("no set for date")
        return out
    qs = doc.get("questions") or []
    out["set_no"] = doc.get("set_no")
    out["nq"] = len(qs)
    out["status"] = doc.get("status")
    if len(qs) != NQ:
        out["problems"].append("question count %d != %d" % (len(qs), NQ))
    seen = set()
    for i, q in enumerate(qs):
        out["problems"] += q_problems(q, i)
        out["warns"].extend(q_warnings(q, i))
        u = str(q.get("uid"))
        if u in seen:
            out["problems"].append("uid repeat inside set: %s" % u)
        seen.add(u)
    # cross-set uid repeat check (one index build shared by the whole pass)
    if index is None:
        index = uid_index(db)
    other = set()
    for k, v in index.items():
        if k != date:
            other |= v
    dup = seen & other
    if dup:
        out["problems"].append("uid repeat across sets: %d (%s)" % (len(dup), sorted(dup)[:2]))
    out["uids"] = sorted(seen)
    out["ok"] = not out["problems"]
    return out


def status(db=None):
    db = db if db is not None else db_handle()[0]
    from collections import Counter
    docs = list(db.afo_sets.find({}, {"date": 1, "status": 1, "set_no": 1, "questions.uid": 1, "used_at": 1}))
    by = Counter(d.get("status") for d in docs)
    allu = set()
    for d in docs:
        allu |= {str(q.get("uid")) for q in (d.get("questions") or [])}
    dates = sorted(d["date"] for d in docs)
    meta = db.afo_supply.find_one({"key": "meta"}) or {}
    gaps = [d for d in datelist(POOL_DATES_FROM, POOL_DATES_TO) if d not in set(dates)]
    return {
        "sets": len(docs), "by_status": dict(by), "from": dates[0] if dates else None,
        "to": dates[-1] if dates else None, "distinct_uids": len(allu),
        "ledger": db.afo_used_q.count_documents({}), "next_set_no": meta.get("next_set_no"),
        "gaps": gaps[:20], "gap_count": len(gaps),
    }


def datelist(a, b):
    d0 = dt.date.fromisoformat(a)
    d1 = dt.date.fromisoformat(b)
    out = []
    while d0 <= d1:
        out.append(d0.isoformat())
        d0 += dt.timedelta(days=1)
    return out


# --------------------------------------------------------------------------- draw / mark
def pick(date, db=None, flush=None, require_audit=True):
    """Return the date's question list. Idempotent: never changes the questions of an existing set.
    Stamps picked_at + status=running. Raises BankError when the set is unusable."""
    dbh = db_handle() if db is None else (db, flush or (lambda: None))
    db, flush = dbh
    a = audit(date, db)
    if not a["ok"]:
        raise BankError("audit failed for %s: %s" % (date, "; ".join(a["problems"][:3])))
    doc = db.afo_sets.find_one({"date": date})
    if doc.get("status") == "used":
        raise BankError("set for %s already used (refusing re-run)" % date)
    db.afo_sets.update_one({"date": date}, {"$set": {
        "status": "running", "picked_at": istnow().strftime("%Y-%m-%d %H:%M:%S")}})
    flush()
    return doc["questions"][:NQ]


def mark(date, db=None, flush=None):
    """After a live test: status=used + used_at, and book the uids in the no-repeat ledger."""
    dbh = db_handle() if db is None else (db, flush or (lambda: None))
    db, flush = dbh
    doc = db.afo_sets.find_one({"date": date})
    if not doc:
        raise BankError("no set to mark for %s" % date)
    now = istnow().strftime("%Y-%m-%d %H:%M:%S")
    db.afo_sets.update_one({"date": date}, {"$set": {"status": "used", "used_at": now}})
    for q in doc.get("questions") or []:
        db.afo_used_q.update_one({"uid": q["uid"]}, {"$set": {"uid": q["uid"], "used_on": date}}, upsert=True)
    flush()
    return len(doc.get("questions") or [])


def build(date, questions, db=None, flush=None, set_no=None):
    """Idempotent insert of a fully-formed 50-Q set. Logs, never posts, never overwrites an existing set."""
    dbh = db_handle() if db is None else (db, flush or (lambda: None))
    db, flush = dbh
    if db.afo_sets.find_one({"date": date}):
        return "exists"
    probs = []
    for i, q in enumerate(questions):
        probs += q_problems(q, i)
    if len(questions) != NQ or probs:
        raise BankError("refusing to build %s: n=%d problems=%s" % (date, len(questions), probs[:3]))
    warns = [w for i, q in enumerate(questions) for w in q_warnings(q, i)]
    if set_no is None:
        meta = db.afo_supply.find_one({"key": "meta"}) or {}
        set_no = int(meta.get("next_set_no", 0)) + 1
    db.afo_sets.insert_one({"date": date, "status": "ready", "set_no": set_no, "questions": questions,
                            "built_at": istnow().strftime("%Y-%m-%d %H:%M:%S"),
                            **({"warns": warns[:10]} if warns else {})})
    db.afo_supply.update_one({"key": "meta"}, {"$set": {"next_set_no": set_no}}, upsert=True)
    flush()
    return "built set_no=%s" % set_no


def supply(frm=POOL_DATES_FROM, to=POOL_DATES_TO, db=None, flush=None):
    """Daily 05:00 IST pass: idempotent audit of coverage + no-repeat.
    Gap-fill only from a Mongo `pool` collection (unused questions) if one exists.
    Today the pool is 100% reserved (2500/2500) and every live date already has a set -> this is a pure audit.
    NEVER posts to Telegram."""
    dbh = db_handle() if db is None else (db, flush or (lambda: None))
    db, flush = dbh
    rep = {"checked": 0, "missing": [], "bad": [], "filled": [], "pool_left": None, "next_set_no": None}
    index = uid_index(db)
    used_uids = {str(x.get("uid")) for x in db.afo_used_q.find({}, {"uid": 1})}
    rep["ledger"] = len(used_uids)
    if "pool" in db.list_collection_names():
        rep["pool_left"] = max(0, db.pool.count_documents({}) - len(used_uids))
    rep["note"] = ("no pool collection: nothing to build; coverage audit only"
                   if "pool" not in db.list_collection_names() else "pool present")
    for d in datelist(frm, to):
        rep["checked"] += 1
        a = audit(d, db, index=index)
        if a.get("warns"):
            rep.setdefault("warned", []).append({"date": d, "n": len(a["warns"]), "why": a["warns"][0]})
        if a["ok"]:
            continue
        if a["problems"] == ["no set for date"]:
            rep["missing"].append(d)
            # gap-fill path (only if a pool collection with unused uids exists in Mongo)
            if "pool" in db.list_collection_names():
                cand = [q for q in db.pool.find({}) if str(q.get("uid")) not in used_uids][:NQ]
                if len(cand) == NQ:
                    build(d, cand, db, flush)
                    rep["filled"].append(d)
        else:
            rep["bad"].append({"date": d, "problems": a["problems"][:3]})
        if a.get("warns"):
            rep.setdefault("warned", []).append({"date": d, "n": len(a["warns"]), "why": a["warns"][0]})
    meta = db.afo_supply.find_one({"key": "meta"}) or {}
    rep["next_set_no"] = meta.get("next_set_no")
    db.afo_supply.update_one({"key": "audit"}, {"$set": {
        "key": "audit", "at": istnow().strftime("%Y-%m-%d %H:%M:%S"),
        "missing": rep["missing"], "bad": rep["bad"], "filled": rep["filled"]}}, upsert=True)
    flush()
    return rep


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    if cmd == "status":
        print(json.dumps(status(), indent=1, default=str))
    elif cmd == "audit":
        print(json.dumps(audit(args[1]), indent=1, default=str))
    elif cmd == "pick":
        qs = pick(args[1])
        print("picked %s: %d questions | first uid=%s" % (args[1], len(qs), qs[0].get("uid")))
    elif cmd == "mark":
        print("marked %s used: %d uids booked" % (args[1], mark(args[1])))
    elif cmd == "supply":
        frm = args[args.index("--from") + 1] if "--from" in args else POOL_DATES_FROM
        to = args[args.index("--to") + 1] if "--to" in args else POOL_DATES_TO
        print(json.dumps(supply(frm, to), indent=1, default=str))
    else:
        print(__doc__)
        sys.exit(2)
