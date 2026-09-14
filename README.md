# ai-learning-companion

I built this for myself, first. I'm learning English and learning to be an AI engineer at the same time, and I didn't want AI-generated code to stay a black box I just trust and copy. This plugin turns real, day-to-day AI-assisted work into small, honest moments of understanding — for the code, and for the language — instead of adding a separate course or app on top of the work you're already doing.

Built with [Claude Code](https://claude.com/claude-code).

It's two Claude Code skills that share one local learner profile.

## ai-learning-companion (the teaching skill)

Watches real AI-assisted work for a genuine teaching moment, across three tracks: an AI-engineering or prompting concept, or a real English struggle in your own messages. When one is genuinely worth it, it teaches at most one thing at a time:

- A new AI-engineering or prompting concept, as a short digest: what changed, why this approach, where it fits, the concept explained plainly, tricky bits demystified, a comprehension check, and a small practice task.
- Or a short English callout: the pattern named, 1-2 real examples from your own messages with corrections — no lecture.

A deterministic cooldown and a priority rule keep this rare and ambient, not noisy: a new AI-engineering concept comes first, then a recurring English struggle, and a one-off English slip only when nothing else qualifies — and it's usually skipped even then.

## Project explorer

A second, independent skill: a structured first-time orientation to an unfamiliar codebase — top-level folders and why, the handful of files worth reading first, anything genuinely unusual about the layout — instead of a file-by-file dump.

Trigger it on demand (slash command explore-project, or just ask "explain this project to me"), or accept the one-line invitation a SessionStart hook offers the first time you open a project it hasn't seen before. It shares the same learner profile (so depth still matches your level), but not the teaching skill's cooldown — the two are unrelated trigger types.

## Explain this

A third, independent skill: a complete explanation of one specific thing you point at — a file, a folder, a code block, a line, a function, or a dependency — covering what it is, what it does, why it's built that way, and anything genuinely non-obvious.

Trigger it on demand (slash command explain-this, or just ask "explain this file" or "what does this dependency do"). Because you asked, it always gives the full explanation at your level, with no cooldown and no shortening for topics you've seen before. It still records the concept in the shared learner profile, so the teaching skill knows you've already met it. For a whole-project overview, it points you to project explorer instead.

## How it works

Everything runs locally: a single JSON file at ~/.claude/ai-learning-companion/profile.json, read and written by a few small Python (stdlib-only) scripts. No server, no network calls, no external dependencies. The level system, the cooldown, and the teaching priority rules are all deterministic code, not something the model decides on its own each time.

## Install

```
/plugin marketplace add ank8dev/ai-learning-companion
/plugin install ai-learning-companion
```

## License

MIT
