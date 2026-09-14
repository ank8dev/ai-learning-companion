---
name: explain-this
description: Use when the user explicitly asks for an explanation of one specific, named thing in the codebase - a file, a folder, a code block, a single line, a function, or a dependency ("explain this file," "what does this function do," "what is this dependency for," "explain line 42"). Always gives the complete explanation at the user's level, regardless of how often the topic has come up before. Not for a whole-project tour or orientation (that's explore-project), and not for ambient teaching moments nobody asked for (that's ai-learning-companion).
---

# Explain This

## Overview

Explains one specific thing the user points at - a file, folder, code block, line, function, or dependency - completely, at their level. Independent of the other two skills in this plugin: it is not a tour (`explore-project`'s job) and not an ambient teaching moment (`ai-learning-companion`'s job). An explicit request always gets a full answer: no cooldown gate, no arbitration, no explanation tiers.

The only thing shared with the other skills is the learner profile at `~/.claude/ai-learning-companion/profile.json`: this skill reads it for depth and records what it explained, so future ambient teaching moments know the topic has been seen.

**Coupling note (intentional, same as project-explorer):** this skill has no scripts of its own. It calls into `../ai-learning-companion/scripts/` for `router.py` and `update_profile.py`, because `profile_lib.py`'s schema/migration logic must live in exactly one place. If the `ai-learning-companion` skill folder is ever renamed or restructured, the script paths below need updating to match.

All script paths below are relative to this skill's own directory (`${CLAUDE_SKILL_DIR}`, e.g. `skills/explain-this/`), reaching into the sibling skill:

```
${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/router.py
${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/update_profile.py
```

## When to Use

**One named target per invocation.** The target is whatever the user pointed at: a file, folder, code block, line, function, or dependency. Naming it is enough. No special syntax needed.

- **Use when:** the user explicitly asks what one specific thing is or does ("explain this file," "what does `safe_write_json` do," "why is `zod` in package.json," or `/explain-this <target>`).
- **Whole-project request** ("explain this whole project," "what's in this repo"): don't give a smaller version of a tour. Say that this skill explains one specific thing, suggest `/explore-project` for the full orientation, and stop.
- **Target unclear** ("explain this" with nothing selected, mentioned, or recently discussed): ask which file, function, or dependency they mean. Don't guess.
- **Several targets in one message:** explain each one fully, one after another. Each one is still its own explicit request.

## Step 1 - Get the context card (reuse, do not reimplement)

```
python3 "${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/router.py"
```

Prints `{"level": ..., "note": ..., "recent_concepts": [...]}`. Use `note` to set how complex your English is. Do not re-derive level logic yourself - this script is the only source of it.

If the profile or script is missing/unreadable, treat it as a fresh/beginner profile and proceed anyway - don't block the explanation on it.

## Step 2 - Read the target

Read the actual target before explaining it: the file or function itself, the folder's contents, the dependency's manifest entry and where the code uses it. Read nearby code only as far as needed to say what the target does and why - don't turn this into exploring the whole project.

## Step 3 - Give the full explanation, every time

**Always the complete explanation.** This is a deliberate difference from `ai-learning-companion`: `explanation_tier` does not apply here, and `times_seen` or earlier history never shortens the answer. The user asked, so they get the whole thing - even if the same topic was taught or explained many times before.

Cover, in this order:

1. **What it is** - the target in plain terms (a config file, a helper function, a validation library, ...).
2. **What it does** - its actual behavior here, in this codebase.
3. **Why it's built or used this way** - the reason or trade-off behind it. Skip this if there's no real reason beyond "that's the only way to do it."
4. **Anything genuinely non-obvious** - a surprising edge case, a hidden dependency, a gotcha. Skip this if nothing is actually non-obvious; don't invent one.

Skip any section with nothing real to say. No comprehension check, no "try it yourself" task - this is a clear answer to a question, not the ambient digest format.

### Language

Same rules as `ai-learning-companion`'s Language section: English only at every level, with complexity set by the context card's `note` (simple English for beginner, normal English with more technical vocabulary for intermediate, full technical English for advanced). Spell out every abbreviation the first time it's used, at every level.

## Step 4 - Record the concept (plain recording, not a teaching moment)

After explaining, if the target involved a real concept worth naming (e.g. `zod`, `git-hooks`, `atomic-write`, `mcp`):

```
python3 "${CLAUDE_SKILL_DIR}/../ai-learning-companion/scripts/update_profile.py" --record-concept "<topic>"
```

- Check `ai_engineering` in `~/.claude/ai-learning-companion/profile.json` first; if an existing topic matches, reuse its exact name so `times_seen` keeps counting on the same entry.
- Don't pass `--status` - a new topic defaults to `seen`, an existing topic keeps its status.
- One call per concept. With several targets, record each one's concept separately.
- **Skip this step entirely if there's no real concept to name** (e.g. explaining one line of arithmetic, or a plain data file). Don't force one into existence just to have something to record.

This is a **plain recording**, exactly like project-explorer's: it only upserts `ai_engineering[topic]` (bumping `times_seen`). It does **not** call `--check`, does not run `--pick` arbitration, and does not touch `teaching_history`, `last_taught_at`, `turns_since_last_teach`, or `sessions_taught`. Never hand-edit `profile.json`. If the script fails, skip the recording silently - the explanation has already been given.

## Common Mistakes

- **Shortening the answer because the topic was seen before.** `explanation_tier` belongs to the ambient skill only. An explicit request always gets the full explanation.
- **Running the request through `--check` or `--pick`.** No gate, no arbitration, no cooldown - an explicit question is always answered. Only `--record-concept` is used, and only after explaining.
- **Using `--track` to record.** That's a teaching event: it resets the ambient cooldown and appends to `teaching_history`. Use `--record-concept`.
- **Doing a mini tour.** A whole-project request goes to `/explore-project`; say so and stop.
- **Adding a quiz or practice task.** Not part of this format.
- **Forcing a concept to record.** No real concept, no `--record-concept` call.
- **Guessing the target.** If it's unclear what "this" is, ask.
