#!/usr/bin/env python3
"""agents/relay.py — marker-file dispatcher (SPEC v11 §7).

Reads .GHA_DISPATCH.json from the repo root, dispatches every requested workflow with the runner's
GITHUB_TOKEN, then clears the marker (API delete = a commit on main). Runs inside keepwarm-agent.yml.

Marker format:
  {"items": [{"wf": "slot-chain.yml", "inputs": {}}, {"wf": "booksend.yml", "inputs": {"job": "iari"}}]}

Rules: never raises, never logs tokens, leaves a malformed marker in place (so nothing is silently lost).
"""
import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "b9811507-del/live-test")
TOK = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
API = "https://api.github.com/repos/" + REPO
MARKER = ".GHA_DISPATCH.json"
HDR = {"Authorization": "Bearer " + TOK, "Accept": "application/vnd.github+json",
       "User-Agent": "agri-quiz-v11-relay", "Content-Type": "application/json"}


def log(*a):
    print("[relay]", *a, flush=True)


def api(method, path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=HDR)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else {}


def main():
    if not TOK:
        log("no GITHUB_TOKEN -> nothing to do")
        return 0
    try:
        d = api("GET", "/contents/" + MARKER)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log("no marker file -> idle")
            return 0
        log("marker read failed HTTP %s" % e.code)
        return 0
    try:
        items = (json.loads(__import__("base64").b64decode(d["content"]).decode()) or {}).get("items") or []
    except Exception as e:
        log("marker malformed (%s) -> leaving it in place for the admin to fix" % str(e)[:80])
        return 0
    if not items:
        log("marker empty -> clearing")
    sent = 0
    for it in items:
        wf = (it or {}).get("wf") or ""
        if not wf:
            continue
        body = {"ref": "main"}
        if it.get("inputs"):
            body["inputs"] = {str(k): str(v) for k, v in it["inputs"].items()}
        try:
            api("POST", "/actions/workflows/%s/dispatches" % wf, body)
            sent += 1
            log("dispatched %s inputs=%s" % (wf, sorted((it.get('inputs') or {}).keys())))
        except urllib.error.HTTPError as e:
            log("dispatch %s failed HTTP %s %s" % (wf, e.code, e.read()[:120].decode(errors="replace")))
        except Exception as e:
            log("dispatch %s error %s" % (wf, str(e)[:100]))
    try:
        api("DELETE", "/contents/" + MARKER, {"message": "relay: marker processed (%d dispatched)" % sent,
                                              "sha": d["sha"]})
        log("marker cleared (dispatched %d item(s))" % sent)
    except Exception as e:
        log("marker clear failed: %s" % str(e)[:100])
    return 0


if __name__ == "__main__":
    sys.exit(main())
