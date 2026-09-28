import json, os, subprocess, sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    os.pardir, "hooks", "verbosity_check.py")
LONG = ("The migration repoints reporting off the deprecated table and onto the "
        "successor, and the row counts reconcile within tolerance. " * 30)   # ~600 words
SHORT = "Done. The query now reads from the successor table."
TABLE = "Here are the results.\n\n" + "| col_a | col_b | col_c | col_d |\n" * 120
CODE = "Here is the patch.\n\n```python\n" + "x = compute_value(a, b, c, d, e)\n" * 200 + "```\n"

def run(payload, env=None):
    e = dict(os.environ); e.pop("TLDR_NUDGE_WORDS", None); e.pop("TLDR_NUDGE_MODE", None)
    e.pop("TLDR_NUDGE_QUIET", None); e.pop("TLDR_NUDGE_SKIP_BUSY", None)
    if env: e.update(env)
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True, env=e)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def base(**kw):
    d = {"session_id": "test-session", "hook_event_name": "Stop",
         "stop_hook_active": False, "last_assistant_message": LONG}
    d.update(kw); return d

CASES = []
def case(name, expect, payload, env=None, raw=None):
    CASES.append((name, expect, payload, env, raw))

case("long answer -> asks",            "ask",    base())
case("short answer -> silent",         "silent", base(last_assistant_message=SHORT))
case("stop_hook_active -> silent",     "silent", base(stop_hook_active=True))
case("background task -> still asks",  "ask",    base(background_tasks=[{"id":"t1","type":"subagent","status":"running"}]))
case("background + SKIP_BUSY -> quiet","silent", base(background_tasks=[{"id":"t1","type":"subagent","status":"running"}]), {"TLDR_NUDGE_SKIP_BUSY":"1"})
case("session cron -> still asks",     "ask",    base(session_crons=[{"id":"c1","schedule":"0 9 * * *","recurring":True}]))
case("120 table rows -> silent",       "silent", base(last_assistant_message=TABLE))
case("200 lines code -> silent",       "silent", base(last_assistant_message=CODE))
case("empty answer -> silent",         "silent", base(last_assistant_message=""))
case("missing answer field -> silent", "silent", {"session_id":"s","hook_event_name":"Stop"})
case("mode=flag -> flag only",         "flag",   base(), {"TLDR_NUDGE_MODE":"flag"})
case("WORDS=0 -> asks on short",       "ask",    base(last_assistant_message=SHORT), {"TLDR_NUDGE_WORDS":"0"})
case("QUIET -> silent",                "silent", base(), {"TLDR_NUDGE_QUIET":"1"})
case("bad threshold -> falls back",    "ask",    base(), {"TLDR_NUDGE_WORDS":"banana"})
case("high threshold -> silent",       "silent", base(), {"TLDR_NUDGE_WORDS":"5000"})

fails = []
for name, expect, payload, env, _ in CASES:
    rc, out, err = run(payload, env)
    if rc != 0:
        fails.append(f"{name}: exit {rc} (expected 0) stderr={err[:120]}"); continue
    if expect == "silent":
        ok = out == ""
        detail = f"stdout={out[:100]!r}"
    else:
        try: j = json.loads(out)
        except Exception: fails.append(f"{name}: stdout not JSON: {out[:120]!r}"); continue
        has_ask = "additionalContext" in json.dumps(j.get("hookSpecificOutput", {}))
        has_msg = bool(j.get("systemMessage"))
        # ask mode: instruction only, no duplicate systemMessage.
        # flag mode: systemMessage only, no instruction.
        ok = (has_ask and not has_msg) if expect == "ask" else (has_msg and not has_ask)
        detail = f"systemMessage={has_msg} additionalContext={has_ask}"
    print(f"{'PASS' if ok else 'FAIL'}  {name:34s} {detail if not ok else ''}")
    if not ok: fails.append(f"{name}: {detail}")

# malformed stdin
p = subprocess.run([sys.executable, HOOK], input="not json at all", capture_output=True, text=True)
print(f"{'PASS' if p.returncode==0 and not p.stdout.strip() else 'FAIL'}  malformed stdin -> silent, exit 0")
if p.returncode != 0 or p.stdout.strip(): fails.append("malformed stdin")

# mute file
d = os.path.expanduser("~/.claude/tldr-nudge"); os.makedirs(d, exist_ok=True)
mp = os.path.join(d, "mute-test-session")
open(mp, "w").close()
rc, out, err = run(base())
print(f"{'PASS' if out=='' else 'FAIL'}  mute file -> silent")
if out: fails.append("mute file not honored")
os.remove(mp)
rc, out, err = run(base())
print(f"{'PASS' if out else 'FAIL'}  mute removed -> asks again")
if not out: fails.append("mute removal not honored")

print()
print(f"{len(CASES)+3-len(fails)}/{len(CASES)+3} passed" if not fails else f"FAILURES:\n" + "\n".join(fails))
