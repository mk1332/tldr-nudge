# tldr-nudge

When Claude finishes an answer that ran long, it asks you whether you want a TL;DR
before the turn ends, and tells you how long the answer was.

```
570 prose words, past the 350 threshold. Call AskUserQuestion now: ...

  TL;DR  That answer ran to 570 words. Want the short version?
  > Yes, TL;DR        Compress it to at most 3 bullets.
    No, it reads fine  Keep the answer as written.
```

Pick yes and you get at most 3 bullets: the decision, the number behind it, any
blocker, written by a cheaper model (Haiku by default, see below). Pick no and the turn ends with nothing further.

## Install

Requires `python3` on your PATH (macOS, Linux, or Windows with Python installed). The
TL;DR is written by `claude -p`, so the `claude` CLI must be on PATH too.

```bash
claude plugin marketplace add mk1332/tldr-nudge
claude plugin install tldr-nudge@mukund-plugins
```

To try it for one session without installing anything:

```bash
claude --plugin-dir ./tldr-nudge
```

After installing, `/reload-plugins` activates it in an open session, and `/hooks`
should list a `Stop` hook pointing at `verbosity_check.py`.

## How it asks rather than just printing

A hook runs a shell command, so it cannot open a prompt itself. What it can do on
`Stop` is return `hookSpecificOutput.additionalContext`, which keeps the turn alive
and hands Claude an instruction. The instruction tells Claude to call
`AskUserQuestion`, which is what puts the real yes/no in front of you.

That costs one model turn per flagged answer. `decision: "block"` would also keep
the turn alive, but the transcript labels it a hook error, which is the wrong
signal for a hook doing its job. `additionalContext` is labelled
`Stop hook feedback` instead.

Claude Code prints that feedback to you, so the instruction is deliberately terse:
About 80 words, one rule per branch. Version 0.3.0 sent 185 words and put a wall of
instructions in front of every three-bullet summary. There is no way to hide it,
since `suppressOutput` is a documented no-op, so the only lever is length. For the
same reason ask mode sends no `systemMessage`: the instruction already opens with
the word count, and saying it twice is noise.

If you would rather spend nothing, set `TLDR_NUDGE_MODE=flag`. You then get the
count as a one-line notice and `/tldr` on demand, with no question and no extra
turn.

## Cheaper model writes the TL;DR

The main model never writes the summary itself. The Stop hook saves the last answer
to `~/.claude/tldr-nudge/last.md`. When you say yes, or run `/tldr`, the hook script
is called with `--summarize`, which pipes that answer to `claude -p --model haiku`
and prints the bullets. The main model only relays them.

A summary is only produced on request. Nothing is generated unprompted, and in
Claude Code's auto permission mode the hook stays silent entirely.

Set `TLDR_NUDGE_MODEL` to any model alias or ID. `inherit` skips the cheap call and
has the session model write it. If `claude` is missing or the call fails, the
session model writes it too.

## What counts as long

Prose words in Claude's final message. Not counted:

- fenced code blocks
- markdown table rows
- tool calls, thinking blocks, and subagent output, none of which reach the hook

A 40-row table is roughly 400 words of nothing but data, and a 300-line diff is not
a verbose answer. Flagging either would teach you to ignore the flag.

The threshold is 350 words, chosen so that answers in the 400 to 900 word range trip
it and ordinary replies stay silent.

## When it stays quiet

| Condition | Why |
|---|---|
| Answer under the threshold | Nothing to compress |
| `stop_hook_active` is true | The TL;DR ends a turn too, and would otherwise re-trigger the question |
| A background task is in flight | Only when `TLDR_NUDGE_SKIP_BUSY` is set. Off by default, see below |
| Claude Code is in auto permission mode | Nobody is there to answer. `TLDR_NUDGE_IN_AUTO` overrides |
| A mute is set by `/tldr off` | You asked it to stop |
| `TLDR_NUDGE_QUIET` is set | Disabled without uninstalling |

A standing session cron is deliberately not a reason to stay quiet. Gating on that
would let one daily scheduled task mute the plugin for good.

Background work in flight is not a reason either, as of 0.3.0. Version 0.2.0 gated
on it, reasoning that the turn was paused rather than finished. That was wrong in
the case that matters most: a long answer lands while agents keep running, you are
sitting there reading it, and that is exactly when you want the offer. Set
`TLDR_NUDGE_SKIP_BUSY` to restore the old behaviour, which is worth having if a
workflow posts a long progress update after every step.

## Muting

```
/tldr off           8 hours
/tldr off forever   until you turn it back on
/tldr on            back on
```

`off` expires on its own so a mute you forget about does not silence the plugin
permanently. The setting lives in `~/.claude/tldr-nudge/mute`, which holds a
duration counted from when the file was written: `8h`, `30m`, `2d`, a bare number
read as hours, or `forever`.

The mute is global rather than per-session, because a slash command has no way to
learn the session id. A `mute-<session_id>` file in the same directory is honored
too, if you are wiring this up from something that does know it.

## Commands

| Command | Effect |
|---|---|
| `/tldr` | Compress the previous answer to at most 3 bullets |
| `/tldr 1` | One line instead of 3 bullets |
| `/tldr off` \| `off forever` \| `on` | Mute or unmute the nudge |

`/tldr-nudge:tldr` is the form that always resolves. The bare `/tldr` is the short
alias a plugin skill normally also gets, but this one sets
`disable-model-invocation`, and whether the alias survives that combination is not
something the docs settle. If `/tldr` does not autocomplete after install, use the
full name.

The flag is worth keeping either way: without it Claude could load this skill on its
own and compress an answer the hook was about to ask you about.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `TLDR_NUDGE_WORDS` | `350` | Prose-word threshold. `0` asks on every answer |
| `TLDR_NUDGE_MODE` | `ask` | `flag` prints the count only and spends no model turn |
| `TLDR_NUDGE_QUIET` | unset | Set to anything to disable |
| `TLDR_NUDGE_SKIP_BUSY` | unset | Stay quiet while a background task is in flight |
| `TLDR_NUDGE_MODEL` | `haiku` | Model that writes the TL;DR. `inherit` uses the session model |
| `TLDR_NUDGE_IN_AUTO` | unset | Nudge even in auto permission mode |
| `TLDR_NUDGE_STATE_DIR` | `~/.claude/tldr-nudge` | Where the mute files and `last.md` live |

Set these in the `env` block of `~/.claude/settings.json`.

## Tests

```bash
python3 tests/run_all.py
```

44 cases over synthetic `Stop` payloads: every gate, the code and table exclusions,
each mute format and its expiry, malformed input, and `--summarize` against a stub
`claude`. They run against a temporary state directory and never touch your real
mute files. The hook exits 0 in all of them: exit 2 from a `Stop` hook blocks the
turn, and any other non-zero code is noisy for a hook that is working as designed.

## License

MIT. See `LICENSE`.
