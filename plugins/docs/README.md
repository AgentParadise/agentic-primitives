# Docs Plugin

Documentation tools for Claude Code agents.

## Skills
- **fuma** — Fumadocs integration and documentation generation
- **system-infographic** — Generate a single self-contained HTML infographic explaining how a system, flow, or architecture works
- **html-guide** — Write a long-form self-contained HTML guide so a specific reader can make a specific decision in a domain whose vocabulary they lack

### Picking between the two HTML skills

Both emit one self-contained `.html` file, but they answer different questions:

| | `system-infographic` | `html-guide` |
|---|---|---|
| Reader absorbs it | in one pass | over a sitting, jumping around |
| Shape | visual poster, diagram-led | long-form document, prose-led |
| Answers | "how does this work" | "what should I decide" |
| Navigation | none needed | floating scroll-spy table of contents |
| Vocabulary | assumed | defined in a table at the top |
