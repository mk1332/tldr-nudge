#!/usr/bin/env python3
"""Stop hook: measure the answer Claude just gave, and if it ran long, make
Claude ask whether you want a TL;DR before the turn ends.

Mechanism: on Stop, return hookSpecificOutput.additionalContext. That keeps the
turn going and hands Claude an instruction, and unlike decision:"block" the
transcript labels it "Stop hook feedback" rather than a hook error. The
instruction tells Claude to call AskUserQuestion, so you get a real yes/no
prompt instead of a line of text you have to act on yourself.

What is counted: prose words in last_assistant_message. Fenced code blocks and
markdown table rows are excluded, because a 40-row table is data, not
verbosity, and flagging it would train you to ignore the flag.

Gates, all of which return silently:
  - stop_hook_active, so the TL;DR turn cannot re-trigger the question
  - background_tasks in flight, but only when TLDR_NUDGE_SKIP_BUSY is set
  - a mute set by /tldr off, which expires after 8 hours by default
  - TLDR_NUDGE_QUIET, to disable without uninstalling

Environment:
  TLDR_NUDGE_WORDS   prose-word threshold, default 350. 0 asks on every answer.
  TLDR_NUDGE_MODE    "ask" (default) prompts via AskUserQuestion.
                     "flag" only prints the one-line count and spends no model turn.
  TLDR_NUDGE_QUIET   set to anything to disable.
  TLDR_NUDGE_SKIP_BUSY  stay quiet while a background task is in flight.

Always exits 0. Exit 2 would block the turn with the message routed as a hook
error, which is the wrong channel for a hook that is working as designed.
"""

import json
import os
import re
import sys
import time

DEFAULT_THRESHOLD = 350
FENCE = re.compile(r"^\s*(```|~~~)")
TABLE_ROW = re.compile(r"^\s*\|")
BULLET = re.compile(r"^([-*+]|\d+\.)\s+\S")
STATE_DIR = os.path.expanduser("~/.claude/tldr-nudge")


DURATION = re.compile(r"^([0-9]*\.?[0-9]+)\s*([mhd])?$", re.I)
UNITS = {"m": 60.0, "h": 3600.0, "d": 86400.0}


def is_muted(session_id):
    """True when /tldr off is in effect.

    Two files are honored. The global one is what /tldr off writes, because a
    slash command has no way to learn the session id. The session-scoped one is
    there for anyone wiring this up from a script that does know it.

    The file holds a duration measured from its own modification time: "8h",
    "30m", "2d", or a bare number read as hours. /tldr off writes 8h so a
    forgotten mute recovers on its own rather than silencing the plugin for
    good, and /tldr on writes 0h to expire it immediately. The word "forever",
    an empty file, or anything unparseable mutes indefinitely, on the grounds
    that a file named mute means mute whatever is inside it.
    """
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    for path in (os.path.join(STATE_DIR, "mute"),
                 os.path.join(STATE_DIR, f"mute-{safe}")):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                spec = fh.readline().strip()
            written = os.path.getmtime(path)
        except OSError:
            continue
        if not spec or spec.lower() == "forever":
            return True
        m = DURATION.match(spec)
        if not m:
            return True
        seconds = float(m.group(1)) * UNITS[(m.group(2) or "h").lower()]
        if time.time() < written + seconds:
            return True
    return False


def measure(text):
    """Prose words outside fenced code and tables, plus structure markers."""
    prose, in_fence = [], False
    headings = bullets = fences = tables = 0
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            fences += 1
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if TABLE_ROW.match(line):
            tables += 1
            continue
        if stripped.startswith("#"):
            headings += 1
        if BULLET.match(stripped):
            bullets += 1
        prose.append(line)
    return {
        "words": len(" ".join(prose).split()),
        "headings": headings,
        "bullets": bullets,
        "code_blocks": fences // 2,
        "table_rows": tables,
    }


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def summary(m, threshold):
    bits = [plural(m["words"], "prose word")]
    if m["headings"]:
        bits.append(plural(m["headings"], "heading"))
    if m["bullets"]:
        bits.append(plural(m["bullets"], "bullet"))
    skipped = []
    if m["code_blocks"]:
        skipped.append(plural(m["code_blocks"], "code block"))
    if m["table_rows"]:
        skipped.append(plural(m["table_rows"], "table row"))
    line = f"verbose: {', '.join(bits)} (threshold {threshold})"
    if skipped:
        line += f", not counting {' and '.join(skipped)}"
    return line


def ask_instruction(m, threshold):
    """The instruction Claude acts on.

    Kept short on purpose. Claude Code shows Stop hook feedback in the
    transcript, so every word here is printed to the user each time the nudge
    fires. The first version ran to 185 words, which put a wall of instructions
    ahead of a three-bullet summary. Only what changes Claude's behaviour earns
    a place: the tool name, the two labels, and one rule per branch.
    """
    return (
        f'{m["words"]} prose words, past the {threshold} threshold. '
        'Call AskUserQuestion now: header "TL;DR", question "That answer ran to '
        f'{m["words"]} words. Want the short version?", options "Yes, TL;DR" and '
        '"No, it reads fine". On yes, at most 3 bullets: the decision and the '
        'number behind it, nothing restated. On no, end the turn silently. Do not '
        "apologise or explain this. If they have said to stop asking, skip it and "
        "say `/tldr off` mutes it."
    )


def main():
    if os.environ.get("TLDR_NUDGE_QUIET"):
        return 0
    # Created here so /tldr off only ever needs echo, never mkdir, and so the
    # mute works before this hook has ever fired.
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except OSError:
        pass
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    # True when Claude Code is already continuing because of a Stop hook. Without
    # this, the TL;DR itself would end a turn and re-trigger the question.
    if payload.get("stop_hook_active"):
        return 0

    # Background work in flight is NOT a reason to stay quiet by default. The
    # first version gated on it, on the theory that the turn was paused rather
    # than finished. Real use disproved that: the common case is a long answer
    # delivered while agents keep running, with you sitting there reading it,
    # and swallowing the nudge there is the one time you wanted it. Set
    # TLDR_NUDGE_SKIP_BUSY to get the old behaviour, which is worth having if a
    # workflow posts a long progress update after each of its steps.
    if os.environ.get("TLDR_NUDGE_SKIP_BUSY") and payload.get("background_tasks"):
        return 0

    if is_muted(payload.get("session_id")):
        return 0

    text = payload.get("last_assistant_message") or ""
    if not text.strip():
        return 0

    try:
        threshold = int(os.environ.get("TLDR_NUDGE_WORDS", DEFAULT_THRESHOLD))
    except ValueError:
        threshold = DEFAULT_THRESHOLD

    m = measure(text)
    if m["words"] < threshold:
        return 0

    # In ask mode the instruction is printed to the user as Stop hook feedback and
    # already opens with the count, so a systemMessage saying it again is noise.
    if os.environ.get("TLDR_NUDGE_MODE", "ask").strip().lower() == "flag":
        out = {"systemMessage": summary(m, threshold) + ". /tldr to compress it"}
    else:
        out = {"hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": ask_instruction(m, threshold),
        }}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
