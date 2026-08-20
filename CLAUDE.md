@AGENTS.md

# Claude Code instructions

The line above is an import, not a request: Claude Code reads `CLAUDE.md`, not
`AGENTS.md`, so the repo's real rulebook is pulled in rather than pointed at.
`AGENTS.md` is under Anthropic's 200-line guidance for memory files, so
importing it whole costs nothing. See https://code.claude.com/docs/en/memory,
section "AGENTS.md".

## Environment

Run the environment doctor and read its JSON instead of probing the environment:

```
python ../ai-command-center/scripts/doctor.py
```

Read-only from here — run it, never write into `ai-command-center`.

The old instruction said `& ..\doctor.ps1`. That file does not exist on Nebula
(checked 2026-08-20); the Python script is the live one.

## Verification

`.claude/settings.json` runs the test suite as a `Stop` hook, so a turn cannot
end on a red suite. If it blocks you, read the stderr it hands back and fix the
cause — do not work around the hook.
