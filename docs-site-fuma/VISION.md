# 📚 agentic-p Documentation Site - Vision

> **Framework:** Fumadocs (Next.js)
> **Hosting:** GitHub Pages (static export)
> **Status:** Active Development

---

## Why Fumadocs?

We chose Fumadocs over Mintlify for:

| Requirement | Fumadocs | Mintlify |
|-------------|----------|----------|
| Self-hosted | ✅ GitHub Pages | ❌ SaaS only |
| Blog support | ✅ Native | ⚠️ Changelog only |
| Cost at scale | ✅ Free forever | ❌ $150+/mo for teams |
| Extensibility | ✅ Full Next.js | ❌ Closed platform |
| Beautiful design | ✅ Modern | ✅ Modern |

---

## Current Features

- ✅ **Documentation** - Full CLI reference, concepts, guides
- ✅ **Mermaid Diagrams** - Architecture visualizations
- ✅ **Search** - Orama static search
- ✅ **Dark Mode** - System-aware theming
- ✅ **Blog** - Foundation ready
- ✅ **GitHub Pages** - Free hosting

---

## Roadmap

### Phase 1: Core Docs ✅
Foundation documentation for agentic-p CLI.

### Phase 2: Blog Content 🔜
- Tutorial posts
- Release announcements
- Deep dives on primitives
- Community spotlights

### Phase 3: Comments Integration 📋
**Planned Integration: Giscus**

```
Why Giscus:
- Free, open-source
- Uses GitHub Discussions (audience already has accounts)
- No ads, no tracking
- Threaded conversations
- Emoji reactions
- Markdown support
```

Implementation:
```tsx
// components/Comments.tsx
import Giscus from '@giscus/react';

export function Comments({ slug }: { slug: string }) {
  return (
    <Giscus
      repo="YourOrg/agentic-primitives"
      repoId="R_..."
      category="Blog Comments"
      categoryId="DIC_..."
      mapping="pathname"
      reactionsEnabled="1"
      theme="dark"
    />
  );
}
```

Add to blog post template:
```tsx
// app/blog/[slug]/page.tsx
import { Comments } from '@/components/Comments';

export default function BlogPost({ params }) {
  return (
    <article>
      <MDXContent />
      <Comments slug={params.slug} />
    </article>
  );
}
```

### Phase 4: Newsletter/Subscribers 📋
**Planned Integration: Buttondown or Resend**

```
Why Buttondown:
- Developer-friendly
- Markdown emails
- Free tier: 100 subscribers
- Simple API
- No tracking pixels by default
```

Implementation:
```tsx
// components/NewsletterSignup.tsx
export function NewsletterSignup() {
  return (
    <form action="https://buttondown.email/api/emails/embed-subscribe/agentic-p" method="post">
      <input type="email" name="email" placeholder="your@email.com" />
      <button type="submit">Subscribe</button>
    </form>
  );
}
```

Features to add:
- Subscribe form on blog index
- Subscribe CTA at end of posts
- RSS feed (already built-in)
- New post notifications

### Phase 5: Analytics 📋
**Options under consideration:**

| Tool | Cost | Privacy |
|------|------|---------|
| Plausible | $9/mo | ✅ Privacy-first |
| Umami | Free (self-host) | ✅ Privacy-first |
| Vercel Analytics | Free tier | ⚠️ Vercel hosting required |

Priority: Low - only add when we need data-driven decisions.

---

## Design Principles

### 1. Beauty Matters
Documentation should be **inspiring**, not boring. We chose Fumadocs for its modern aesthetic that rivals Mintlify.

### 2. Developer Experience First
- Fast search
- Code-first examples
- Copy-paste friendly
- Dark mode default

### 3. No Vendor Lock-in
Everything is self-hosted, open-source, and portable. We own our content and infrastructure.

### 4. Community-Centric
Comments and discussions happen where developers already are (GitHub). No friction, no new accounts.

### 5. Progressive Enhancement
Start simple, add features as needed:
1. Docs → Done
2. Blog → Foundation ready
3. Comments → When we have readers
4. Newsletter → When we have subscribers
5. Analytics → When we need data

---

## Development

```bash
# Run locally
just docs

# Build static site
just docs-build

# Check for broken links
just docs-check
```

---

## Contributing

See [Maintaining Docs](/docs/maintaining/overview) for:
- Mermaid diagram standards
- Writing style guide
- Component usage
- Code example best practices

---

## Questions?

Open an issue or discussion on GitHub.
