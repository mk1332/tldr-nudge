---
name: tldr
description: Compress the previous answer to its decisions and numbers, or mute the tldr-nudge verbosity prompt. Run as /tldr, /tldr 1, /tldr off, /tldr off forever, or /tldr on.
argument-hint: "[1 | off | off forever | on]"
allowed-tools: Bash(echo:*)
disable-model-invocation: true
---

Argument: $ARGUMENTS

## If the argument is `off`, `off forever`, or `on`

You are changing the nudge setting, not compressing anything. Run one command and
report the result in a single line. Do not compress the previous answer.

- `off`: `echo 8h > ~/.claude/tldr-nudge/mute`
  Then say: nudge off for 8 hours, `/tldr on` to re-enable.
- `off forever`: `echo forever > ~/.claude/tldr-nudge/mute`
  Then say: nudge off until `/tldr on`.
- `on`: `echo 0h > ~/.claude/tldr-nudge/mute`
  Then say: nudge back on.

The file holds a duration counted from when it was written, so `8h` means eight
hours from now and `0h` expires immediately. Do not use `rm` or `mkdir` here; the
Stop hook creates the directory, and `echo` alone is enough.

## Otherwise, compress my immediately preceding answer

Do not re-derive it, do not research anything, and do not apologise for the length.

- At most 3 bullets. If the argument is `1`, one line instead.
- Keep only what changes what I do: the decision, the number that supports it, and
  any blocker. Drop reasoning, caveats I did not ask about, and alternatives you
  already rejected.
- Lead with the plain answer, then the figure. "Not worth it: 1 of 71 cases needed
  it" beats "partial-answerability was 1 of 71".
- If the answer was already short enough to read once, say so in one line rather
  than restating it.
