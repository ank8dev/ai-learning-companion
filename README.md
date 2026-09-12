# ai-learning-companion

A Claude Code skill that turns the code Claude just wrote for you into a short teaching moment — so you build real understanding of your own codebase instead of treating AI-generated code as a black box.

After a meaningful change (a real decision, a new concept, or non-obvious code — not typos, renames, or formatting), it gives you a short digest covering:

- What changed, in plain language
- Why this approach was chosen over alternatives
- Where it fits in the project's architecture
- Any new concepts, explained simply
- English polish on your own messages (grammar, articles, prepositions — real errors only)
- A quick comprehension check
- A small practice task

It keeps a lightweight learner profile at `~/.claude/ai-learning-companion/profile.json` (no server, just a local JSON file) so known terms stop being re-explained, and explanations shift more toward plain English as the profile grows.

## Install

```
/plugin marketplace add ank8dev/ai-learning-companion
/plugin install ai-learning-companion
```

## License

MIT
