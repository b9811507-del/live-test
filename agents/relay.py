"""GHA dispatch relay — called by keepwarm chain every ~4 min.

Reads .GHA_DISPATCH.json ({"items":[{"wf":"slot-chain.yml","inputs":{}}]}), dispatches
each workflow via the runner's GITHUB_TOKEN (PAT on this repo lacks actions:write),
then removes the marker and pushes the removal. Failed items stay in the file and are
retried next cycle. No-ops silently when no marker exists.
"""
import json, os, subprocess, sys, urllib.request

MARKER = os.path.join(os.path.dirname(__file__), "..", ".GHA_DISPATCH.json")
REPO = os.environ.get("GITHUB_REPOSITORY") or "b9811507-del/live-test"
TOK = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def dispatch(wf, inputs):
    body = json.dumps({"ref": "main", "inputs": inputs or {}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/dispatches",
        method="PUT", data=body,
        headers={"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json"})
    urllib.request.urlopen(req, timeout=15)


def main():
    if not os.path.exists(MARKER) or not TOK:
        return
    try:
        items = json.load(open(MARKER)).get("items", [])
    except Exception:
        items = []
    left = []
    for it in items:
        try:
            dispatch(it["wf"], it.get("inputs"))
            print("dispatched:", it["wf"])
        except Exception as e:
            print("fail:", it["wf"], str(e)[:100])
            left.append(it)
    git = lambda *a: subprocess.run(("git",) + a, capture_output=True, text=True, check=False)
    if left:
        json.dump({"items": left}, open(MARKER, "w"))
        git("add", ".GHA_DISPATCH.json")
    else:
        os.remove(MARKER)
        git("rm", "-q", "--cached", ".GHA_DISPATCH.json")
        git("commit", "-q", "-m", "relay consumed marker", "--allow-empty") if False else None
    git("-c", "user.name=live-test-bot", "-c", "user.email=bot@local", "commit", "-qm", "gha dispatch relay")
    p = f"https://runner:{TOK}@github.com/{REPO}"
    r = git("push", "-q", p, "HEAD:main")
    if r.returncode != 0:
        git("fetch", "-q", p, "main")
        git("rebase", "-q", "FETCH_HEAD")
        git("push", "-q", p, "HEAD:main")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("relay err:", str(e)[:150])
    sys.exit(0)   # never fail the keepwarm job
