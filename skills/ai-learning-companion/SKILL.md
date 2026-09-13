---
name: ai-learning-companion
description: Use after any moment of real AI-assisted work — not just a finished code change — where a genuine AI-engineering/prompting concept, a genuine recurring English struggle, or (rarely) a one-off English slip appeared, and the teaching-cooldown gate is open. Not for small talk, a single minor typo, a concept already at "practiced" status, mid-task partial work, or anything still inside the cooldown gate.
---

# AI Learning Companion

## Overview

Turns a moment of real AI-assisted work into a short teaching moment, so the developer builds real understanding — of the engineering, of working with AI, and of their own English — instead of treating AI-generated output as a black box. V3 widens this beyond finished code changes (V2's trigger) to any real AI-assisted work, across three tracks (AI-engineering, prompting, English), gated by a cooldown and arbitrated so at most one thing is ever taught per moment.

## When to Use

Judge by what actually happened, not by whether a code diff exists.

- **Use when**, this turn, at least one of these is genuinely true:
  - A **new or under-practiced AI-engineering concept** appeared — a library, pattern, protocol, workflow, or engineering decision (e.g. MCP, context engineering, git strategy, deployment, debugging approach, agents/subagents, tools & skills — topics are free-form, not a fixed list).
  - A **genuine prompting lesson** appeared — a real decision about how a prompt/instruction to an AI was structured, worded, or scoped, and why.
  - A **recurring English struggle** showed up again in the user's own messages (the same kind of mistake seen before).
  - Rarely, a **one-off English slip** worth a quick correction, when nothing else qualifies.
- This can happen after a finished feature/fix/refactor (V2's trigger, unchanged, still qualifies on its own), but also mid-conversation: reviewing an AI-generated plan, discussing an architecture choice, debugging together, drafting or refining a prompt for another AI/agent, or any other real AI-assisted work.
- **Skip when:**
  - Small talk, acknowledgements, or a message with no real engineering or English content.
  - A single minor typo with nothing else going on.
  - The only candidate concept is already at `"practiced"` status.
  - The teaching-cooldown gate says no (see below) — a hard skip, not a judgment call.
  - Same V2 exclusions still apply: typo fixes, pure renames, formatting-only changes, mid-task partial work with more steps coming, or an explicit "skip this" from the user.

**"It's only N lines" is still not a reason to skip a genuine AI-engineering decision.** But "something happened" is also not a reason to teach — the gate and arbitration below decide that, not a feeling that this moment seems important.

## Learner Profile & Teaching Gate

All script paths below resolve relative to this skill's base directory (the path Claude Code showed when this skill was invoked).

### Step 1 — Get the context card (unchanged from V2)

```
python3 scripts/router.py
```

Prints `{"level": ..., "note": ..., "recent_concepts": [...]}`, computed deterministically from `~/.claude/ai-learning-companion/profile.json`. It also transparently creates or upgrades that file if it's missing or in an old shape — you never need to read or edit its raw contents for this step. Use `note` for the English/user's-language mix (see "Language" below); don't re-derive the thresholds yourself.

### Step 2 — Notice candidates for this turn

Before touching the gate, look at what actually happened this turn and list every genuine candidate:
- Any new or under-`"practiced"` AI-engineering/prompting concept — read `ai_engineering` from `~/.claude/ai-learning-companion/profile.json` directly (same convention as V2's `known_terms` check) to see a topic's current status; a topic absent from the dict counts as new.
- Any English struggle pattern in the user's own messages since the last digest (chat, comments, commit messages) — check against the literal checklist: missing/wrong articles, wrong or missing verb forms (including a missing "to" before an infinitive), subject-verb agreement, wrong prepositions, wrong word order. Read `struggle_patterns` directly from profile.json — if your observation matches an existing entry, reuse its exact wording so it's recognized as the same pattern.
- Any plain new vocabulary word worth noting.

If you found none of these, stop here — there's nothing to gate or arbitrate, and no script call is needed this turn.

### Step 3 — Check the gate (hard, before deciding what to teach)

```
python3 scripts/update_profile.py --check [--observe-pattern "<pattern text>" ...]
```

Pass one `--observe-pattern` per English struggle noticed in Step 2 (recurring or brand-new) — this records the occurrence (bumping its count) even on a turn where nothing ends up being taught, so a pattern can still reach the tier-2 threshold later. This call always advances the internal counter and always writes.

Reads back `{"can_teach": bool, "turns_since_last_teach": N, "min_gap": N}`.

**If `can_teach` is `false`: stop. No digest, no mention of it to the user.** This is a hard gate, checked before any decision about what to teach — not a suggestion to weigh against how important this moment feels.

### Step 4 — Arbitrate (only if the gate is open)

Build one `--candidate "track:topic"` per Step-2 candidate (`track` is `ai_engineering`, `prompting`, or `english`; for a recurring struggle, reuse the exact wording already in `struggle_patterns`):

```
python3 scripts/router.py --pick --candidate "ai_engineering:mcp" --candidate "english:missing article before uncountable noun"
```

Reads back `{"winner": {"track", "topic", "priority", "optional"}}` or `{"winner": null}`.

**Arbitration priority (fixed rule, not a judgment call):**
1. **A genuine new AI-engineering/prompting concept** — highest priority; this is the main goal of this skill. Beats everything except a topic already at `"practiced"` status.
2. **A recurring English struggle pattern** (seen 2+ times, not re-taught recently) — beats a one-off slip.
3. **A one-off English slip or plain vocabulary word** — lowest priority, considered only when nothing above qualifies. `optional: true` on this tier means **usually skip it too** — teach it only when a quick correction is clearly worth the interruption, never for a single throwaway typo.

**If `winner` is `null`: stop.** The gate was open but nothing this turn actually earned a teaching moment — expected and fine, don't force one.

**Only ever act on the single winner returned.** Never teach more than one track/topic in the same turn, even if several candidates genuinely looked worth teaching.

### Step 5 — Record the event (after teaching; never hand-edit profile.json)

Exactly one call, matching the winner's track:

```
# ai_engineering / prompting:
python3 scripts/update_profile.py --track ai_engineering --topic "mcp" --status seen \
  --term "mcp" --term "<any other newly-covered term>" --task-type <refactor|newfeature|bugfix|...>

# english, recurring pattern:
python3 scripts/update_profile.py --track english --pattern "missing article before uncountable noun"

# english, one-off slip taught as vocabulary:
python3 scripts/update_profile.py --track english --term "<word or phrase>"
```

- `--status` moves a topic from `seen` → `understood` → `practiced` as your judgment of the user's grasp improves; omit it to leave an existing topic's status as-is (a brand-new topic defaults to `seen`). Status never moves down.
- When the winner is `ai_engineering`/`prompting`, also pass `--term "<topic>"` for that same topic — this is a deliberate V3 choice: it counts toward `known_terms`/level progression the same as any other covered term, so the level now reflects everything taught across all three tracks, not just code vocabulary.
- Still pass any other V2-style `--term`/`--task-type` for unrelated newly-covered terms from the same turn — that part is unchanged from V2 and isn't gated by any of the above.
- This script is the only thing allowed to change `profile.json`. It resets the teaching cooldown, appends to `teaching_history`, and (for ai_engineering/prompting) updates the topic's status — in the same single atomic write as the V2 term/level update. **Never hand-edit `profile.json` directly.**

If `profile.json` or any script is missing, unreadable, or fails for any reason, treat it as a fresh/beginner profile and skip the digest entirely — don't block on it, don't mention the error to the user.

## What to Produce

Produce exactly one of the two formats below, matching the arbitration winner. Skip any part that has nothing real to say — don't pad it.

### Format A — AI-engineering or prompting concept (`winner.track` is `ai_engineering` or `prompting`)

The V2 code-digest format, unchanged, minus the English section — English never rides along in the same turn, since only one track teaches per gated moment:

1. **What changed** — plain-language summary of what happened this turn (a diff, a plan, a debugging exchange, a prompt draft — whatever it actually was).
2. **Why this approach** — the reasoning or trade-off behind the choice. Skip if there was only one reasonable way to do it.
3. **Where it fits** — which files or parts of the system this relates to, if applicable.
4. **The concept** — explain `winner.topic` in plain language, at the depth implied by its current status (a first-time `seen` topic gets more setup than one already `understood`). Other concepts that merely appear in passing don't get their own deep explanation this turn — that would be teaching more than one thing at once.
5. **Tricky bits, demystified** — briefly explain any genuinely non-obvious parts. Skip if nothing is actually tricky.
6. **Comprehension check** — 2-5 questions about what was just covered (mix "what would happen if..." with "why did we...").
7. **Try it yourself** — one small, self-contained task to extend or apply what was just covered. Propose it; don't do it for them.

### Format B — English (`winner.track` is `english`)

Short. Not a lecture:
1. Name the pattern in one line (e.g. "missing article before uncountable noun").
2. Show 1-2 real examples from the user's own recent messages, each with the corrected version next to it, and a short reason only when the fix isn't obvious.
3. Nothing else — no comprehension check, no "try it yourself," no unrelated code commentary.

### Language (unchanged from V2)

Reply in the literal language of the user's most recent messages. **"The user's language" means the literal language they actually typed — never a guessed native language.** If they're typing in English, reply in English, full stop, no matter how rough that English is; rough English is exactly what Format B is for, not a reason to switch languages. For Format A, follow the router's `note` for the right English/user's-language mix.

## Common Mistakes

- **Firing on every micro-edit.** Still applies — the widened trigger is about the *quality* of a candidate moment, not how often you check for one.
- **Skipping the gate check.** `can_teach: false` means stop, full stop — don't rationalize teaching anyway because this one feels important.
- **Teaching more than one track at once.** Even when both a new concept and a recurring English pattern are genuinely present, only the arbitration winner gets taught this turn.
- **Turning Format A into a code review.** This is for the user's learning, not critiquing the code's quality.
- **Turning Format B into a grammar lecture.** Name it, show 1-2 examples, stop.
- **Answering the quiz questions yourself.** Ask them and let the user think — don't immediately follow up with the answers.
- **Forgetting to record the event.** Every digest must end with the matching `update_profile.py --track ...` call, or the gate never resets and `teaching_history`/status never advance.
- **Teaching an `optional: true` tier-3 English slip by default.** It exists so nothing fires when it's truly the only candidate — but "available" isn't "worth it"; skip more often than not.
- **"Their English is rough, I'll just reply in their native language instead."** Still the opposite of helping — it removes their only chance to practice. See Language above.
- **"The grammar errors felt minor, so I skipped it."** If it reached tier 2 (count >= 2) or you're already producing Format B, teach it plainly — the literal checklist decides, not a felt sense of "minor."
