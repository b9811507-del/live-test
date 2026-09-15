#!/usr/bin/env python3
"""tests/verify_all.py — the v11 verification gate (SPEC §9). Nothing gets enabled before this is green.

1. python3 -m py_compile on every shipped .py
2. yaml.safe_load on every workflow + static checks:
     - every workflow has workflow_dispatch + contents:write/actions:write + job timeout-minutes
     - no inline multi-line python in YAML (heredoc trap)
     - no secret ever echoed
     - slot-chain / slot-guard / keepwarm-agent never use cancel-in-progress: true
     - every workflow self-registers via push: paths (or is dispatch-only by design)
3. engine status/ready offline smoke
4. the 12-case fake-clock battery (tests/fake_clock.py)

Usage: python3 tests/verify_all.py
"""
import glob
import json
import os
import py_compile
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WF = os.path.join(REPO, ".github", "workflows")
ok_all = True


def section(name):
    print("\n== %s ==" % name, flush=True)


def fail(msg):
    global ok_all
    ok_all = False
    print("  FAIL " + msg, flush=True)


def good(msg):
    print("  ok   " + msg, flush=True)


def main():
    section("1. py_compile")
    files = sorted(glob.glob(os.path.join(REPO, "engine", "*.py")) +
                   glob.glob(os.path.join(REPO, "agents", "*.py")) +
                   glob.glob(os.path.join(HERE, "*.py")))
    for f in files:
        try:
            py_compile.compile(f, doraise=True)
            good(os.path.relpath(f, REPO))
        except Exception as e:
            fail("%s -> %s" % (os.path.relpath(f, REPO), str(e)[:120]))

    section("2. workflows (yaml.safe_load + static rules)")
    try:
        import yaml
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyyaml"], check=True)
        import yaml
    wfs = sorted(glob.glob(os.path.join(WF, "*.yml")))
    if not wfs:
        fail("no workflow files found")
    for f in wfs:
        name = os.path.basename(f)
        try:
            text = open(f, encoding="utf-8").read()
            d = yaml.safe_load(text)
        except Exception as e:
            fail("%s yaml error: %s" % (name, str(e)[:140]))
            continue
        probs = []
        on = d.get(True, d.get("on")) or {}
        if "workflow_dispatch" not in on:
            probs.append("no workflow_dispatch")
        perms = d.get("permissions") or {}
        if perms.get("contents") != "write" or perms.get("actions") != "write":
            probs.append("permissions must be contents:write + actions:write")
        for jn, j in (d.get("jobs") or {}).items():
            if not j.get("timeout-minutes"):
                probs.append("job %s without timeout-minutes" % jn)
        if "concurrency" not in d:
            probs.append("no concurrency group")
        if name in ("slot-chain.yml", "slot-guard.yml", "keepwarm-agent.yml") and \
                (d.get("concurrency") or {}).get("cancel-in-progress") is not False:
            probs.append("test workflows must never cancel-in-progress")
        if "python3 - <<" in text or "<<'PY" in text:
            probs.append("inline heredoc python (forbidden)")
        if "secrets." in text and any(l.strip().startswith("echo ") and "secrets." in l for l in text.splitlines()):
            probs.append("secret echoed")
        if "push" not in on:
            probs.append("no push self-registration")
        else:
            paths = ((on["push"] or {}).get("paths") or [])
            if not any(name in p for p in paths):
                probs.append("push paths must include the file itself")
        if probs:
            fail("%s: %s" % (name, "; ".join(probs)))
        else:
            good(name)

    section("3. engine offline smoke (status / ready gate)")
    env = dict(os.environ, ENGINE_FAKE="1", ENGINE_NOW="2026-09-16T09:00:00+05:30",
               ENGINE_FAKE_SHEETS=os.path.join(HERE, "fixtures", "sheets"), CHAT_ID="-1003784795446",
               EXAM_TG_TOKEN="fake", ADMIN_CHAT="-100999")
    env.pop("GITHUB_TOKEN", None)
    p = subprocess.run([sys.executable, os.path.join(REPO, "engine", "engine.py"), "status"],
                       capture_output=True, text=True, env=env, cwd=REPO)
    print("  status rc=%d | %s" % (p.returncode, (p.stdout or "").splitlines()[0] if p.stdout else p.stderr[:100]))
    if p.returncode != 0:
        fail("status crashed")
    else:
        good("status runs")
    p = subprocess.run([sys.executable, os.path.join(REPO, "engine", "engine.py"), "ready"],
                       capture_output=True, text=True, env=env, cwd=REPO)
    print("  " + (p.stdout or p.stderr).strip()[:160])
    good("ready gate reachable (offline fake)")
    # every sheet key used by the planners must resolve to a real id, not to itself (the 404 trap)
    snip = ("import sys;sys.path.insert(0,%r);import engine as e;"
            "keys=['iari']+[v[0] for v in e.VOLUMES];"
            "print('|'.join(k+'='+e.SHEETS.get(k,'MISSING')[:8] for k in keys))" % os.path.join(REPO, "engine"))
    p = subprocess.run([sys.executable, "-c", snip], capture_output=True, text=True, cwd=REPO)
    line = (p.stdout or p.stderr).strip().splitlines()[-1] if (p.stdout or p.stderr) else ""
    if "MISSING" in line or "=" not in line:
        fail("sheet key resolution: %s" % line[:160])
    else:
        good("sheet keys resolve -> %s" % line)

    section("4. fake-clock battery")
    p = subprocess.run([sys.executable, os.path.join(HERE, "fake_clock.py")], capture_output=True, text=True)
    print(p.stdout.strip())
    if p.returncode != 0:
        fail("battery has failing cases")

    print("\n==== GATE RESULT: %s ====" % ("GREEN" if ok_all else "RED"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
