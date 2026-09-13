# ai-learning-companion

A Claude Code skill that turns real AI-assisted work into short teaching moments — so you build real understanding of AI engineering, prompting, and your own English, instead of treating AI-generated output as a black box.

It watches for a genuine teaching moment across three tracks — an AI-engineering/prompting concept, or an English struggle in your own messages — and, when one is genuinely worth it, teaches **at most one thing at a time**:

- A new AI-engineering or prompting concept, in the original digest format: what changed, why this approach, where it fits, the concept explained plainly, tricky bits demystified, a comprehension check, and a small practice task.
- Or a short English callout: the pattern named, 1-2 real examples from your own messages with corrections — no lecture.

A deterministic cooldown gate and priority rule keep it rare and ambient rather than noisy: AI-engineering concepts come first, then a recurring English struggle, and a one-off English slip only when nothing else qualifies (and usually gets skipped even then).

It keeps a lightweight learner profile at `~/.claude/ai-learning-companion/profile.json` (no server, just a local JSON file, Python stdlib only) so known concepts stop being re-explained, and explanations shift more toward plain English as the profile grows.

### Project explorer

A second, independent skill: a structured first-time orientation to an unfamiliar codebase — top-level folders and why, the handful of files worth reading first, anything genuinely unusual about the layout — instead of a file-by-file dump. Trigger it on demand (`/explore-project`, or just ask "explain this project to me"), or accept the one-line invitation a `SessionStart` hook offers the first time you open a project it hasn't seen before. It shares the same learner profile (so depth still matches your level), but not the ambient teaching skill's cooldown — the two are unrelated trigger types.

## Install

```
/plugin marketplace add ank8dev/ai-learning-companion
/plugin install ai-learning-companion
```

## License

MIT
