import json, os, subprocess, sys, time
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    os.pardir, "hooks", "verbosity_check.py")
LONG = ("The migration repoints reporting onto the successor table and the counts reconcile. " * 60)
D = os.path.expanduser("~/.claude/tldr-nudge"); os.makedirs(D, exist_ok=True)
G, S = os.path.join(D, "mute"), os.path.join(D, "mute-sess1")

def run():
    e = {k: v for k, v in os.environ.items() if not k.startswith("TLDR_NUDGE")}
    p = subprocess.run([sys.executable, HOOK], env=e, capture_output=True, text=True,
        input=json.dumps({"session_id": "sess1", "hook_event_name": "Stop",
                          "stop_hook_active": False, "last_assistant_message": LONG}))
    return p.returncode, p.stdout.strip()

def check(label, want_silent, write=None, path=None, age=0):
    for f in (G, S):
        if os.path.exists(f): os.remove(f)
    if write is not None:
        open(path, "w").write(write)
        if age: os.utime(path, (time.time() - age, time.time() - age))
    rc, out = run()
    ok = rc == 0 and ((out == "") == want_silent)
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    return ok

r = []
r.append(check("no mute file -> asks", False))
r.append(check("'8h' written now -> silent", True, "8h\n", G))
r.append(check("'8h' written 9h ago -> asks", False, "8h\n", G, age=9*3600))
r.append(check("'30m' written 10m ago -> silent", True, "30m", G, age=600))
r.append(check("'30m' written 40m ago -> asks", False, "30m", G, age=2400))
r.append(check("'2d' written 1d ago -> silent", True, "2d", G, age=86400))
r.append(check("'0h' (what /tldr on writes) -> asks", False, "0h\n", G))
r.append(check("bare '8' read as hours -> silent", True, "8", G))
r.append(check("'forever' -> silent", True, "forever\n", G))
r.append(check("empty file -> silent", True, "", G))
r.append(check("garbage -> silent (fails closed)", True, "banana\n", G))
r.append(check("session-scoped mute honored", True, "forever", S))
for f in (G, S):
    if os.path.exists(f): os.remove(f)
r.append(check("cleared -> asks", False))
print(f"\n{sum(r)}/{len(r)} passed")
