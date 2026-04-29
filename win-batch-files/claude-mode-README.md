# Claude Code Mode Switcher

A menu-driven Windows command-line tool for switching Claude Code between
Anthropic direct (claude.ai) and AWS Bedrock (BYOM) providers.

## Files

| File | Committed | Purpose |
|---|---|---|
| `claude-mode.cmd` | Yes | Entry point — run this from any cmd window |
| `claude-mode.config.example.cmd` | Yes | Config template — copy and fill in |
| `claude-mode.config.cmd` | No (gitignored) | Your personal config |

## Setup

1. Copy the example config:

   ```cmd
   copy win-batch-files\claude-mode.config.example.cmd win-batch-files\claude-mode.config.cmd
   ```

2. Edit `claude-mode.config.cmd` with your AWS profile names and Bedrock model IDs.

3. Ensure `win-batch-files\` is on your `PATH` (or run from that directory).

4. Run:

   ```cmd
   claude-mode
   ```

## Usage

The menu shows your current active provider and lets you switch:

```
+==========================================+
|  Claude Code -- Mode Switcher             |
+==========================================+

  Active :  Bedrock  (profile-1  |  us-east-1)

  Select provider:

  [1]  Anthropic  (claude.ai)
  [2]  profile-1
  [3]  profile-2

  [Q] Quit
```

- **Anthropic** — clears all Bedrock env vars and runs `claude login` to
  authenticate via claude.ai browser flow.
- **Bedrock profile** — prompts for model selection, then sets
  `CLAUDE_CODE_USE_BEDROCK`, `AWS_PROFILE`, `AWS_REGION`, and
  `ANTHROPIC_MODEL` for both the current session (`set`) and permanently
  (`setx` / registry).

## Environment variables managed

| Variable | Anthropic | Bedrock |
|---|---|---|
| `CLAUDE_CODE_USE_BEDROCK` | cleared | `1` |
| `AWS_PROFILE` | cleared | e.g. `profile-1` |
| `AWS_REGION` | cleared | e.g. `us-east-1` |
| `ANTHROPIC_MODEL` | cleared | e.g. `us.anthropic.claude-sonnet-4-6` |

## Config format

```cmd
set "CFG_BEDROCK_COUNT=2"

set "CFG_P1_NAME=profile-1"
set "CFG_P1_AWS_PROFILE=profile-1"
set "CFG_P1_REGION=us-east-1"
set "CFG_P1_MODEL_COUNT=2"
set "CFG_P1_M1=us.anthropic.claude-sonnet-4-6|Sonnet 4.6"
set "CFG_P1_M2=us.anthropic.claude-opus-4-6-v1|Opus 4.6"
```

Model IDs use the Bedrock cross-region inference profile format.
Find yours at: **AWS Console → Bedrock → Cross-region inference**.

## After switching providers

`setx` writes to the Windows user registry — new processes pick it up
automatically. The current session also gets the change via `set`.
**Restart VS Code** (full close, not Reload Window) to apply to the IDE.

Verify usage via CloudTrail:

```cmd
aws cloudtrail lookup-events --region us-east-1 --profile profile-1 ^
  --lookup-attributes AttributeKey=EventSource,AttributeValue=bedrock.amazonaws.com ^
  --max-results 5
```

## Known limitations / planned work

- The current `.cmd` implementation works but cmd.exe is inherently fragile.
  **Planned rewrite:** PowerShell (`.ps1`) with a thin `.cmd` stub — zero
  dependencies, native JSON config, proper registry access, better UI.
- **No usage limits or cost controls.** Connecting directly to Bedrock means
  no rate limiting — a single developer could run up significant charges.
  An abstraction/proxy layer with per-user quotas is required before
  broad rollout across DOT.
