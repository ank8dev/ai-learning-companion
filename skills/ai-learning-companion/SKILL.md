---
name: ai-learning-companion
description: Use after completing a feature, fix, or refactor the user asked for, before moving to the next task — including small diffs, as long as a real decision, new concept, or non-obvious code was involved. Not for typo fixes, pure renames, formatting-only changes, mid-task partial work, or exploratory reads with no code change.
---

# AI Learning Companion

## Overview

Turns the code you just wrote into a short teaching moment, so the developer builds real understanding of the codebase instead of treating AI-generated code as a black box.

## When to Use

Judge by what happened in the change, not by how many lines it took.

- **Use when:** you just finished a feature, bugfix, or refactor the user asked for, and it involved a decision (why this approach over another), a new concept (a library, pattern, or language feature), or non-obvious code. A two-line input-validation guard qualifies — deciding where to check, what to raise, and fail-fast-vs-silent are real engineering decisions even though the diff is short.
- **Skip when:** the change is a typo fix, pure rename, formatting-only change, config value tweak, mid-task partial work with more steps coming, or the user has explicitly asked you to move fast and skip this. A hundred-line mechanical rename skips too — size alone doesn't earn a digest.

**"It's only N lines" is not a reason to skip.** Ask instead: was there a decision, a new concept, or non-obvious code here? If yes, teach it regardless of size.

## Learner Profile

Before producing the digest, run the router to get the current context card:

```
python3 scripts/router.py
```

(resolve `scripts/router.py` relative to this skill's base directory — the path Claude Code showed when this skill was invoked). This prints a small JSON object, e.g. `{"level": "intermediate", "note": "...", "recent_concepts": [...]}`, computed deterministically from `~/.claude/ai-learning-companion/profile.json`. It also transparently creates or upgrades that file if it's missing or in an old shape — you never need to read or edit its raw contents for this.

Use the card like this:
- `note` already tells you the right English/user's-language mix for this digest — follow it directly, don't re-derive the known-term thresholds yourself.
- `recent_concepts` are the learner's most recently covered terms — useful for continuity ("last time you learned X, this builds on it"), not required in every digest.
- To decide whether a specific term appearing in this diff is known or new (for "New concepts" below), read `known_terms` from `~/.claude/ai-learning-companion/profile.json`: a term already present is **known** — use it plainly in English, don't re-explain or translate it; a term absent is **new** — explain it simply, and note it as newly-covered for the update step below.
- **"The user's language" means the literal language of their most recent messages — never a guessed native language.** If they are typing in English, the digest is in English, full stop, no matter how rough that English is. Rough English is what the "English polish" section is for, not a reason to answer in a different language. Switching languages because their English has mistakes defeats the entire point of this skill — it removes their English practice instead of supporting it.
- After writing the digest, run the update script once (even if no terms were new — this is what advances `sessions_taught`):

```
python3 scripts/update_profile.py --term "<newly-covered term>" --term "<another>" --task-type <refactor|newfeature|bugfix|...>
```

Pass one `--term` flag per newly-covered term from this digest (omit entirely if none), and `--task-type` if this session's work clearly fits a category (optional). This script is the only thing allowed to change `profile.json` — it adds the terms, increments `sessions_taught`, and re-runs the level logic (with hysteresis, so level never flips from a single session) before saving. **Never hand-edit `profile.json` directly.**

If `profile.json` or either script is missing, unreadable, or fails for any reason, treat it as a fresh/beginner profile — don't block the digest on it, don't mention the error to the user.

## What to Produce

Before moving on, give the user a short digest covering the parts below, in order. Skip any part that has nothing real to say — don't pad it.

1. **What changed** — plain-language summary of the diff.
2. **Why this approach** — the reasoning or trade-off behind the choice. Skip if there was only one reasonable way to do it.
3. **Where it fits** — which files were touched and how they relate to the rest of the project's structure.
4. **New concepts** — technologies, patterns, or language features that appear in this diff, each with a one-line plain-language explanation, per the Learner Profile rules above.
5. **English polish** — check the user's own messages since the last digest (chat, comments, commit messages) for concrete grammar errors: missing/wrong articles, wrong or missing verb forms (including a missing "to" before an infinitive), subject-verb agreement, wrong prepositions, wrong word order. **Any one of these present is enough to include this section — do not use a subjective "is this rough enough" judgment call, use this literal checklist.** Pick 1-3 of the affected sentences, show the corrected version next to the original, and give a short reason when the fix isn't obvious. Only skip this section if a check against the list above finds zero matches — don't skip because the errors "felt minor."
6. **Tricky bits, demystified** — briefly explain any genuinely non-obvious lines. Skip if nothing is actually tricky.
7. **Comprehension check** — 2-5 questions about the change just made (mix "what would happen if..." with "why did we...").
8. **Try it yourself** — one small, self-contained task the user could do to extend or modify what was just built. Propose it; don't do it for them.

Reply in the literal language of the user's most recent messages, adjusted per the Learner Profile. Never switch to a different language because their English contains mistakes.

## Common Mistakes

- **Firing on every micro-edit.** This becomes noise fast — apply judgment on what counts as a "meaningful chunk."
- **Turning it into a code review.** This is for the user's learning, not critiquing the code's quality.
- **Answering the quiz questions yourself.** Ask them and let the user think — don't immediately follow up with the answers.
- **Correcting English that's already fine.** English polish is for sentences that actually read wrong, not for stylistic nitpicks — over-correcting makes it noise instead of help.
- **Skipping the profile update.** Every digest must run `update_profile.py` at the end, even with zero new terms, or `sessions_taught` never advances and the learner's level can't progress.
- **"Their English is rough, I'll just reply in their native language instead."** Reality: this is the opposite of helping — it removes their only chance to practice. Rough English gets corrected via "English polish," in English. The reply language always matches what they actually typed, never a guessed native language.
- **"The grammar errors felt minor, so I skipped English polish."** Reality: run the literal checklist (articles, verb forms, agreement, prepositions, word order) — a felt sense of "minor" is not a valid reason to skip. One matching error is enough to include the section.
