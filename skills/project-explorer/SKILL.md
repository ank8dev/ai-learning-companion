---
name: explore-project
description: Use when the user explicitly asks for a structured tour or orientation to the current codebase ("explain this project to me," "give me a tour," "walk me through this codebase," "what's where in this repo") - or when a SessionStart hook has already offered a one-line first-time tour invitation and the user answers it. Produces a structured overview (top-level folders and why, the handful of files that actually matter, anything genuinely unusual) instead of a file-by-file dump. Not for answering a question about one specific file or folder once a tour has already happened - that's normal follow-up conversation, not this skill.
---

# Project Explorer

## Overview

Gives a new-to-you codebase a structured orientation - what's where, and why - instead of dumping every file. Independent of the `ai-learning-companion` skill's ambient teaching system: different trigger type (on-demand + a one-time session-start offer, not ambient), and it never touches that skill's cooldown gate or arbitration. The two skills share one thing only: the same learner profile at `~/.claude/ai-learning-companion/profile.json`, so depth still matches what the profile already knows.

**Coupling note (intentional, documented - not a silent assumption):** this skill has no scripts of its own. It calls into `../ai-learning-companion/scripts/` for `router.py` and `update_profile.py`, because `profile_lib.py`'s schema/migration logic must live in exactly one place, and duplicating it here would risk the two copies drifting apart. If the `ai-learning-companion` skill folder is ever renamed or restructured, this skill's script paths (and the `SessionStart` hook's) need updating to match.

All script paths below are relative to this skill's own directory (`${CLAUDE_SKILL_DIR}`, e.g. `skills/project-explorer/`), reaching into the sibling skill:

```
${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/router.py
${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/update_profile.py
```

## When to Use

- **Use when:**
  - The user explicitly asks for an orientation/tour/walkthrough of the current project.
  - A `SessionStart` hook already printed a one-line invitation ("This looks like a new project - want a quick walkthrough of what's where?") and the user answers it - either way, see Step 0 below.
- **Skip when:**
  - The user asks about one specific file or function - that's normal conversation, not a tour.
  - No hook invitation was offered and the user hasn't asked for one - never run the full walkthrough unasked.

## Step 0 - Only if a hook invitation was just offered

If your immediately-preceding turn's context included the tour invitation from the `SessionStart` hook, this turn is the user's answer to it:

- **User declines** ("no," "not now," "skip it," etc.): do not run the tour. Just record the decline so the invitation doesn't reappear every session in this project:
  ```
  python3 "${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/update_profile.py" --decline-tour "$PWD"
  ```
  Acknowledge briefly and stop. The user can still ask for a tour later at any time - a decline only suppresses the automatic offer, never the on-demand trigger.
- **User accepts**: continue with Step 1 below, using the current project root as the path.

If no invitation was offered this session, skip Step 0 entirely - you're here because the user asked on-demand.

## Step 1 - Get the context card (reuse, do not reimplement)

```
python3 "${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/router.py"
```

Prints `{"level": ..., "note": ..., "recent_concepts": [...]}`. Use `level`/`note` to calibrate depth exactly as the `ai-learning-companion` skill does: terser and more assumption-heavy at `advanced`, more setup and plainer language at `beginner`. Do not re-derive level logic yourself - this script is the only source of it.

If the profile or script is missing/unreadable, treat it as a fresh/beginner profile and proceed anyway - don't block the tour on it.

## Step 2 - Explore, but stay structural

Look at what's actually there: top-level folders, manifest/config files (`package.json`, `pyproject.toml`, `Cargo.toml`, `.claude-plugin/`, etc.), obvious entry points (`main.*`, `index.*`, `app.*`, `cli.*`), README/docs. Read enough of each to say what it's for - don't read every file, and don't produce a full file listing.

## Step 3 - Produce the overview

Structure, not exhaustiveness:

1. **Top-level folders** - what each one is for, one line each.
2. **The handful of files that actually matter to start reading** - entry points, config, main modules. Not every file; the ones a newcomer should open first.
3. **Anything genuinely unusual or non-obvious about the layout** - skip this section if nothing is actually unusual; don't invent a "quirk."
4. **An explicit invitation to go deeper** - the user can ask about any specific file or folder next, and that becomes ordinary follow-up conversation, not a special mode of this skill.

Explain in English, with complexity set by the context card's `note`, same rule as `ai-learning-companion`'s Language section.

## Step 4 - Record any real new concept (plain recording, not a teaching moment)

If the tour surfaced a genuine AI-engineering concept the profile doesn't know about yet (e.g. this project uses Docker, a monorepo layout, tRPC, a specific deployment pattern):

```
python3 "${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/update_profile.py" --record-concept "<topic>"
```

This is a **plain recording**, not a `ai-learning-companion` V3 teaching moment: it only upserts `ai_engineering[topic]` (status defaults to `seen`, never moves down). It does **not** call `--check`, does not run V3's arbitration, does not touch `teaching_history`, `last_taught_at`, `turns_since_last_teach`, or `sessions_taught`. The two skills share the data; they do not share the gate. Skip this step entirely if nothing genuinely new came up - don't force a concept just to have something to record.

## Step 5 - Mark the project toured

Always do this last, once the overview has actually been given (whether triggered on-demand or after a Step-0 acceptance):

```
python3 "${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/update_profile.py" --mark-toured "$PWD"
```

Safe to call even if the project was already toured (idempotent - keeps the original `first_toured_at`). Use the actual project root you toured, not a subfolder, if they differ.

## Common Mistakes

- **Running the full tour on the hook's invitation alone.** The hook only offers one line; wait for the user's yes before doing Step 1 onward.
- **Treating a "no" as nothing to record.** Without `--decline-tour`, the same invitation reappears next session - call it even on a decline.
- **Calling `--record-concept` through the V3 gate.** It's a separate flag for a reason - never route this through `update_profile.py --check` or `--track`.
- **Dumping every file.** This skill's whole point is structure over exhaustiveness - resist listing everything just because you found it.
- **Forgetting `--mark-toured`.** Without it, the hook keeps offering the invitation every session in this project.
