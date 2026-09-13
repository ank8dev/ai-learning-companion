---
name: ai-learning-companion
description: Use before running a genuinely new or important command (git, deployment, package managers, build tools), or after any moment of real AI-assisted work — not just a finished code change — where something worth explaining appeared (would explaining it help the user explain their own project to someone else?), a genuine recurring English struggle showed up, or (rarely) a one-off English slip, and the teaching-cooldown gate is open. Not for small talk, trivial commands like ls/cd/cat, cosmetic-only changes, a single minor typo, a concept already at "practiced" status, mid-task partial work, or anything still inside the cooldown gate.
---

# AI Learning Companion

## Overview

Turns a moment of real AI-assisted work into a short teaching moment, so the developer builds real understanding — of the engineering, of working with AI, and of their own English — instead of treating AI-generated output as a black box. V3 widens this beyond finished code changes (V2's trigger) to any real AI-assisted work, across three tracks (AI-engineering, prompting, English), gated by a cooldown and arbitrated so at most one thing is ever taught per moment.

## When to Use

Judge by what actually happened, not by whether a code diff exists.

### The one test (AI-engineering and prompting)

**Would explaining this help the user explain their own project to someone else?** If yes, it's a candidate. If no, skip it.

This is the only filter for AI-engineering and prompting candidates, whatever the moment looks like: a code change, a command being run, a dependency being added, a new file or folder, a new concept (an API, an MCP connection), an architecture decision, a prompting choice, or any other real AI-engineering work. It only decides what *can* be a candidate. The gate and arbitration below still decide whether anything gets taught.

- **Yes:** running `git init` in a fresh project. "What's that `.git` folder?" is a question they'll get asked.
- **Yes:** adding `zod` to validate API input, because it explains why bad requests get rejected.
- **Yes:** moving logic out of a route handler into a `services/` folder, because that's how the project is organized.
- **No:** `ls`, `cd`, `cat`. There's nothing about the project to explain.
- **No:** reformatting, renaming a variable, or changing a color.
- **No:** another routine `git commit` once commits are already understood.

Not a candidate in any category: routine repeats of something already understood, cosmetic-only changes, trivial shell navigation. Don't re-judge practiced topics or cooldowns here; the gate and arbitration already handle those.

### English (unchanged)

- A **recurring English struggle** showed up again in the user's own messages (the same kind of mistake seen before).
- Rarely, a **one-off English slip** worth a quick correction, when nothing else qualifies.

### Skip

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

Prints `{"level": ..., "note": ..., "recent_concepts": [...]}`, computed deterministically from `~/.claude/ai-learning-companion/profile.json`. It also transparently creates or upgrades that file if it's missing or in an old shape — you never need to read or edit its raw contents for this step. Use `note` for how complex your English should be (see "Language" below); don't re-derive the thresholds yourself.

### Step 2 — Notice candidates for this turn

Before touching the gate, look at what actually happened this turn and list every genuine candidate:
- Anything that passes the one test above, as an `ai_engineering` or `prompting` topic — read `ai_engineering` from `~/.claude/ai-learning-companion/profile.json` directly (same convention as V2's `known_terms` check) to see a topic's current status; a topic absent from the dict counts as new.
- Any English struggle pattern in the user's own messages since the last digest (chat, comments, commit messages) — check against the literal checklist: missing/wrong articles, wrong or missing verb forms (including a missing "to" before an infinitive), subject-verb agreement, wrong prepositions, wrong word order. Read `struggle_patterns` directly from profile.json — if your observation matches an existing entry, reuse its exact wording so it's recognized as the same pattern.
- Any plain new vocabulary word worth noting.
- **Translated messages don't count for English.** If a user message starts with a marker like `[t]` or `(translated)` (any capitalization), skip it entirely for the two English bullets above: no struggle patterns, no `--observe-pattern`, no vocabulary. Only unmarked messages are real signal for the English track. The marker doesn't affect AI-engineering or prompting candidates.

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

Reads back `{"winner": {"track", "topic", "priority", "optional"}}` or `{"winner": null}`. An `ai_engineering`/`prompting` winner also carries `"explanation_tier"` (`full`, `short`, `reminder`, `mention`, or `silent`), which sets how long the explanation is (see "What to Produce"). Use it as given; don't work it out from `times_seen` yourself.

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
- **A `silent` winner is still recorded**, with `--status practiced`, even though nothing was shown. That hands the topic to the tier-1 `"practiced"` filter, so it stops winning arbitration from then on.
- When the winner is `ai_engineering`/`prompting`, also pass `--term "<topic>"` for that same topic — this is a deliberate V3 choice: it counts toward `known_terms`/level progression the same as any other covered term, so the level now reflects everything taught across all three tracks, not just code vocabulary.
- Still pass any other V2-style `--term`/`--task-type` for unrelated newly-covered terms from the same turn — that part is unchanged from V2 and isn't gated by any of the above.
- This script is the only thing allowed to change `profile.json`. It resets the teaching cooldown, appends to `teaching_history`, and (for ai_engineering/prompting) updates the topic's status — in the same single atomic write as the V2 term/level update. **Never hand-edit `profile.json` directly.**

If `profile.json` or any script is missing, unreadable, or fails for any reason, treat it as a fresh/beginner profile and skip the digest entirely — don't block on it, don't mention the error to the user.

### Commands

Before running a command that passes the one test (git operations, deployment, package managers, build tools), run Steps 3–4 **before** the command, with it as an ordinary candidate (`--candidate "ai_engineering:git-init"`). There's no separate tracking or cooldown for commands.

- If it wins, explain it once at the tier `--pick` returned, then run the command yourself as normal. Never ask the user to type it.
- **One explanation per moment, at every tier.** Whether that explanation was `full`, `short`, a `reminder` line, or a `mention`, don't repeat or summarize it again after the command runs or in a later wrap-up. It was this moment's teaching. Record it with Step 5 as usual.
- If the gate is closed or the command doesn't win, just run it without comment.
- Name command topics as tool plus action (`git-init`, `vercel-deploy`, `npm-install`) and reuse the exact same name next time, so `times_seen` keeps counting.

## What to Produce

Produce exactly one of the two formats below, matching the arbitration winner. Skip any part that has nothing real to say — don't pad it.

### Format A — AI-engineering or prompting concept (`winner.track` is `ai_engineering` or `prompting`)

Length depends on `winner.explanation_tier`. It applies the same way to concepts, prompting, and commands. English never rides along in the same turn, since only one track teaches per gated moment.

| `explanation_tier` | Topic recorded before | Produce |
|---|---|---|
| `full` | never | The full digest below, items 1–7. For a command, deliver it as one block before running the command. |
| `short` | 1–3 times | What it is and why it matters right now, in a few sentences. No comprehension check, no "try it yourself." |
| `reminder` | 4–10 times | One short reminder line. |
| `mention` | 11–24 times | At most one brief clause folded into the normal reply, and only if it really helps this moment. Otherwise nothing. |
| `silent` | 25+ times | Nothing at all. Still record it (see Step 5). |

Full digest (`full` tier only):

1. **What changed** — plain-language summary of what happened this turn (a diff, a command, a plan, a debugging exchange, a prompt draft — whatever it actually was).
2. **Why this approach** — the reasoning or trade-off behind the choice. Skip if there was only one reasonable way to do it.
3. **Where it fits** — which files or parts of the system this relates to, if applicable.
4. **The concept** — explain `winner.topic` in plain language, from the ground up since it's being taught for the first time. Other concepts that merely appear in passing don't get their own deep explanation this turn — that would be teaching more than one thing at once.
5. **Tricky bits, demystified** — briefly explain any genuinely non-obvious parts. Skip if nothing is actually tricky.
6. **Comprehension check** — 2-5 questions about what was just covered (mix "what would happen if..." with "why did we...").
7. **Try it yourself** — one small, self-contained task to extend or apply what was just covered. Propose it; don't do it for them.

### Format B — English (`winner.track` is `english`)

Short. Not a lecture:
1. Name the pattern in one line (e.g. "missing article before uncountable noun").
2. Show 1-2 real examples from the user's own recent unmarked messages (never one starting with `[t]` or `(translated)`), each with the corrected version next to it, and a short reason only when the fix isn't obvious.
3. Nothing else — no comprehension check, no "try it yourself," no unrelated code commentary.

### Language

**Teaching output is always in English only, at every level.** This covers Format A at every tier, and Format B. It holds no matter how rough the user's English is or what language they typed in. Rough English is exactly what Format B is for, not a reason to switch languages.

What changes with level is how complex the English is, never the language. Follow the router's `note`:
- **Beginner:** simple English. Short sentences, plain everyday words.
- **Intermediate:** normal English with more technical vocabulary. Briefly explain a genuinely new or advanced word the first time you use it.
- **Advanced:** full technical English, no simplification.

**Abbreviations, at every level:** the first time an explanation uses an abbreviation (MCP, API, CLI, …), spell out the full term, then say in one short sentence what it means, e.g. "MCP (Model Context Protocol) is a standard way for an AI tool to connect to outside tools and data." Don't assume the acronym is known. Spelling it out costs one sentence, even for an advanced user.

## Common Mistakes

- **Firing on every micro-edit.** Still applies — the widened trigger is about the *quality* of a candidate moment, not how often you check for one.
- **Skipping the gate check.** `can_teach: false` means stop, full stop — don't rationalize teaching anyway because this one feels important.
- **Ignoring `explanation_tier`.** A `reminder` topic gets one line, not a full digest, even when the moment feels big. The tier comes from the script, not from judgment.
- **Explaining a command twice.** One explanation before running it, at whatever tier, then nothing more about it: not after the output, not in a closing summary.
- **Asking the user to type a command themselves.** Explain it, then run it.
- **Teaching more than one track at once.** Even when both a new concept and a recurring English pattern are genuinely present, only the arbitration winner gets taught this turn.
- **Turning Format A into a code review.** This is for the user's learning, not critiquing the code's quality.
- **Turning Format B into a grammar lecture.** Name it, show 1-2 examples, stop.
- **Answering the quiz questions yourself.** Ask them and let the user think — don't immediately follow up with the answers.
- **Forgetting to record the event.** Every digest must end with the matching `update_profile.py --track ...` call, or the gate never resets and `teaching_history`/status never advance.
- **Teaching an `optional: true` tier-3 English slip by default.** It exists so nothing fires when it's truly the only candidate — but "available" isn't "worth it"; skip more often than not.
- **"Their English is rough (or they typed in another language), so I'll explain in their language instead."** Teaching output is English only, always — switching removes their chance to practice. Make the English simpler instead. See Language above.
- **Using an acronym without spelling it out.** "Set up the MCP server" teaches nothing if MCP was never expanded. Spell it out the first time, at every level.
- **Reading a `[t]` / `(translated)` message as English signal.** It was translated, so its grammar and vocabulary aren't the user's own. Skip it for the English track.
- **"The grammar errors felt minor, so I skipped it."** If it reached tier 2 (count >= 2) or you're already producing Format B, teach it plainly — the literal checklist decides, not a felt sense of "minor."
