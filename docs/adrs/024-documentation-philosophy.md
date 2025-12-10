# ADR-024: Documentation Philosophy & Platform Strategy

**Status:** Accepted
**Date:** 2024-12-09
**Authors:** agentic-p team

## Context

The agentic-p project requires comprehensive documentation that serves multiple audiences:
- **New users** learning to use the CLI
- **Contributors** understanding the architecture
- **Community** following project development

We evaluated several documentation platforms and needed to make a strategic decision that balances:
- Design quality and user experience
- Self-hosting capabilities and vendor independence
- Extensibility for future features (blog, comments, newsletter)
- Cost at scale as the team grows

## Decision

We adopt **Fumadocs** (Next.js-based documentation framework) with the following architecture:

### Platform Choice

| Requirement | Decision |
|-------------|----------|
| **Framework** | Fumadocs |
| **Hosting** | GitHub Pages (static export) |
| **Search** | Orama (static, client-side) |
| **Diagrams** | Mermaid via `@theguild/remark-mermaid` |

### Rejected Alternative: Mintlify

Mintlify was initially implemented but rejected due to:
- **SaaS-only hosting** - No self-hosting option
- **Cost at scale** - $150+/month for team features
- **Limited extensibility** - Cannot add comments, newsletter, or custom features
- **Changelog only** - No full blog support

### Design Philosophy

1. **Beauty is Non-Negotiable**
   - Documentation should be inspiring, not utilitarian
   - Modern aesthetic with thoughtful typography
   - Dark mode as default (developer preference)

2. **Developer Experience First**
   - Fast, client-side search
   - Code-first examples with syntax highlighting
   - Copy-paste friendly snippets
   - Mermaid diagrams for architecture visualization

3. **No Vendor Lock-in**
   - Static export to GitHub Pages
   - All content in MDX (portable)
   - Open-source tooling only

4. **Community-Centric**
   - Comments via GitHub Discussions (Giscus) - planned
   - Newsletter for announcements - planned
   - All interactions where developers already are

### Content Architecture

```
docs-site/
├── content/
│   ├── docs/           # Documentation
│   │   ├── index.mdx   # Introduction
│   │   ├── concepts/   # Core concepts
│   │   ├── cli/        # CLI reference
│   │   ├── guides/     # Tutorials
│   │   ├── reference/  # Technical reference
│   │   └── maintaining/ # Contributor docs
│   └── blog/           # Blog posts
├── app/                # Next.js app
└── public/             # Static assets
```

### Mermaid Diagram Standards

All architecture diagrams use Mermaid with consistent styling:

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {
  'primaryColor': '#6366F1',
  'primaryTextColor': '#000',
  'primaryBorderColor': '#4F46E5',
  'lineColor': '#818CF8'
}}}%%
```

### Future Roadmap

| Phase | Feature | Integration |
|-------|---------|-------------|
| 1 | Core Docs | ✅ Complete |
| 2 | Blog | Fumadocs native |
| 3 | Comments | Giscus (GitHub Discussions) |
| 4 | Newsletter | Buttondown or Resend |
| 5 | Analytics | Plausible or Umami |

## Consequences

### Positive

- **Zero hosting costs** - GitHub Pages is free
- **Unlimited contributors** - Anyone can push via Git
- **Full control** - Can add any Next.js feature
- **Beautiful output** - Modern, inspiring design
- **Future-proof** - Blog, comments, newsletter all possible
- **Portable content** - MDX works with any framework

### Negative

- **Migration effort** - Required moving from Mintlify
- **Maintenance burden** - We manage the infrastructure
- **Learning curve** - Team needs Fumadocs/Next.js knowledge

### Neutral

- **Build step required** - Static export before deployment
- **No WYSIWYG editor** - All edits via Git/MDX

## Implementation

See `PROJECT-PLAN_20251209_fumadocs-migration.md` for detailed migration steps.

## References

- [Fumadocs Documentation](https://fumadocs.dev/)
- [Giscus - GitHub Discussions Comments](https://giscus.app/)
- [Buttondown Newsletter](https://buttondown.email/)
- [Mermaid Diagrams](https://mermaid.js.org/)
- [VISION.md](/docs-site/VISION.md) - Detailed future roadmap
