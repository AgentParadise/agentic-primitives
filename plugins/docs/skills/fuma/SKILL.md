---
description: Fumadocs styling patterns and component guidelines
model: sonnet
allowed-tools: Read, Write
---

# Fumadocs Documentation Styling

Comprehensive guide for creating beautiful, consistent documentation using Fumadocs with our established design patterns.

## Purpose

*Level 2 (Workflow)*

Standardize documentation styling across all Fumadocs-based sites with reusable components, theme-aware designs, and interactive elements.

## Technology Stack

| Package | Purpose |
|---------|---------|
| `fumadocs-ui` | Core UI components |
| `fumadocs-core` | Source/loader utilities |
| `fumadocs-mdx` | MDX content processing |
| `three` | 3D graphics library |
| `@react-three/fiber` | React renderer for Three.js |
| `@react-three/drei` | Useful helpers for R3F |
| `lucide-react` | Professional icon library |
| `tailwindcss` | Utility-first CSS |

## Brand Colors

Our primary color palette follows a purple/indigo gradient theme:

```css
/* Brand Colors - Purple/Indigo Theme */
--brand-primary: #818cf8;      /* indigo-400 */
--brand-secondary: #a78bfa;    /* violet-400 */
--brand-accent: #c084fc;       /* purple-400 */
--brand-pink: #f472b6;         /* pink-400 */
--brand-cyan: #22d3ee;         /* cyan-400 */
--brand-emerald: #34d399;      /* emerald-400 */
```

## Custom Components

### 1. Badge Component

Pill-style badges with Lucide icons for highlighting features.

```tsx
// components/Badge.tsx
'use client';
import { cn } from '@/lib/cn';
import { Bot, Package, Plug, Zap, Shield, Sparkles } from 'lucide-react';

type BadgeVariant = 'default' | 'purple' | 'indigo' | 'pink' | 'cyan' | 'green' | 'bright';
type IconName = 'bot' | 'package' | 'plug' | 'zap' | 'shield' | 'sparkles';

const variants = {
  default: 'bg-fd-muted text-fd-muted-foreground border-fd-border',
  purple: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  indigo: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
  pink: 'bg-pink-500/20 text-pink-400 border-pink-500/30',
  cyan: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  green: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  bright: 'bg-gradient-to-r from-violet-500/30 to-purple-500/30 text-purple-300 border-purple-400/40',
};

const iconMap: Record<IconName, LucideIcon> = {
  bot: Bot, package: Package, plug: Plug, zap: Zap, shield: Shield, sparkles: Sparkles,
};

export function Badge({ children, variant = 'default', icon, className }: BadgeProps) {
  const Icon = icon ? iconMap[icon] : null;
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border', variants[variant], className)}>
      {Icon && <Icon className="w-3.5 h-3.5" />}
      {children}
    </span>
  );
}
```

**Usage in MDX:**
```mdx
<Badge variant="indigo" icon="bot">AI-Native</Badge>
<Badge variant="purple" icon="package">Version Controlled</Badge>
```

### 2. GradientButton Component

CTA buttons with gradient backgrounds matching our theme.

```tsx
// components/GradientButton.tsx
'use client';
import Link from 'next/link';
import { ArrowRight, Rocket, Terminal, BookOpen, Zap } from 'lucide-react';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'bright';
type IconName = 'rocket' | 'terminal' | 'book' | 'zap';

const variants = {
  primary: 'bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 text-white shadow-lg shadow-indigo-500/25',
  secondary: 'bg-gradient-to-r from-slate-700 to-slate-800 hover:from-slate-600 hover:to-slate-700 text-white',
  outline: 'border-2 border-fd-foreground/20 hover:border-fd-foreground/40 text-fd-foreground hover:bg-fd-foreground/5',
  bright: 'bg-gradient-to-r from-violet-500 to-purple-500 hover:from-violet-600 hover:to-purple-600 text-white font-semibold shadow-lg shadow-purple-500/30',
};

export function GradientButton({ href, children, variant = 'primary', icon }) {
  const Icon = icon ? icons[icon] : null;
  return (
    <Link href={href} className={cn('inline-flex items-center gap-2 px-5 py-2.5 rounded-full font-medium text-sm transition-all', variants[variant])}>
      {Icon && <Icon className="w-4 h-4" />}
      {children}
      <ArrowRight className="w-4 h-4" />
    </Link>
  );
}
```

**Usage in MDX:**
```mdx
<ButtonGroup>
  <GradientButton href="/docs/quickstart" variant="bright" icon="rocket">
    Get Started
  </GradientButton>
  <GradientButton href="/docs/cli" variant="outline" icon="terminal">
    CLI Reference
  </GradientButton>
</ButtonGroup>
```

### 3. FeatureCard Component

Cards for highlighting key features with gradient backgrounds.

```tsx
// components/FeatureCard.tsx
const gradients = {
  indigo: 'from-indigo-500/10 to-indigo-500/5 border-indigo-500/20 hover:border-indigo-500/40',
  purple: 'from-purple-500/10 to-purple-500/5 border-purple-500/20 hover:border-purple-500/40',
  pink: 'from-pink-500/10 to-pink-500/5 border-pink-500/20 hover:border-pink-500/40',
  cyan: 'from-cyan-500/10 to-cyan-500/5 border-cyan-500/20 hover:border-cyan-500/40',
};

export function FeatureCard({ icon, title, description, gradient = 'indigo' }) {
  return (
    <div className={cn('group rounded-xl border bg-gradient-to-br p-5 transition-all hover:scale-[1.02]', gradients[gradient])}>
      <div className="flex items-start gap-4">
        <div className={cn('flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br', iconGradients[gradient])}>
          <Icon className="w-6 h-6 text-white" />
        </div>
        <div className="space-y-1">
          <h3 className="font-semibold text-fd-foreground">{title}</h3>
          <p className="text-sm text-fd-muted-foreground">{description}</p>
        </div>
      </div>
    </div>
  );
}
```

### 4. PrimitiveCard Component

Cards for displaying primitive types with color-coded styling.

```tsx
// components/PrimitiveCard.tsx
const colorStyles = {
  indigo: {
    bg: 'bg-indigo-500/10 dark:bg-indigo-500/20',
    border: 'border-indigo-500/30',
    badge: 'bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 border-indigo-500/40',
    iconBg: 'bg-indigo-500/20',
    icon: 'text-indigo-600 dark:text-indigo-400',
  },
  // ... similar for purple, pink, cyan, green
};

export function PrimitiveCard({ icon, name, description, invocation, color }) {
  return (
    <div className={cn('relative rounded-xl border p-4 transition-all hover:scale-[1.02]', styles.bg, styles.border)}>
      {/* Icon + Name */}
      {/* Description */}
      {/* Invocation badge */}
    </div>
  );
}
```

## Three.js Hero Scene

Interactive 3D header for landing pages with theme-aware colors.

### Key Features

1. **Theme-aware colors** - Detects light/dark mode and adjusts palette
2. **Animated network nodes** - Rotating mesh of connected points
3. **Floating particles** - Background depth with orbital movement
4. **Central core** - Glowing icosahedron with pulsing animation
5. **Orbital rings** - Rotating TorusGeometry elements

### Color Palettes

```typescript
const DARK_COLORS = {
  core: '#a78bfa',      // violet-400
  coreGlow: '#7c3aed',  // violet-600
  ring1: '#818cf8',     // indigo-400
  ring2: '#c084fc',     // purple-400
  node: '#a5b4fc',      // indigo-300
  line: '#6366f1',      // indigo-500
  particle: '#c7d2fe',  // indigo-200
};

const LIGHT_COLORS = {
  core: '#7c3aed',      // violet-600
  coreGlow: '#6d28d9',  // violet-700
  ring1: '#4f46e5',     // indigo-600
  ring2: '#9333ea',     // purple-600
  node: '#4338ca',      // indigo-700
  line: '#6366f1',      // indigo-500
  particle: '#6366f1',  // indigo-500
};
```

### Theme Detection Hook

```typescript
function useTheme() {
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    const checkTheme = () => {
      setIsDark(document.documentElement.classList.contains('dark'));
    };
    checkTheme();
    const observer = new MutationObserver(checkTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  return isDark;
}
```

### Usage

```mdx
import { HeroScene } from '@/components/HeroScene';

<HeroScene />
```

## Global CSS Enhancements

Add to `app/global.css`:

```css
/* Enhanced card hover effects */
.fd-card { transition: all 0.2s ease; }
.fd-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 30px rgba(99, 102, 241, 0.15);
}
.dark .fd-card:hover {
  box-shadow: 0 8px 30px rgba(129, 140, 248, 0.2);
}

/* Accordion styling */
.dark [data-state="open"]>button {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.1));
}

/* Code block borders */
pre { border: 1px solid rgba(99, 102, 241, 0.2) !important; }
.dark pre { border: 1px solid rgba(129, 140, 248, 0.2) !important; }

/* Link hover effects */
article a:not([class]) {
  text-decoration-color: rgba(99, 102, 241, 0.4);
  transition: text-decoration-color 0.2s ease;
}
article a:not([class]):hover {
  text-decoration-color: rgba(99, 102, 241, 1);
}
```

## MDX Components Registration

Register all custom components in `mdx-components.tsx`:

```typescript
import defaultMdxComponents from 'fumadocs-ui/mdx';
import { HeroScene } from '@/components/HeroScene';
import { Badge } from '@/components/Badge';
import { FeatureCard, FeatureGrid } from '@/components/FeatureCard';
import { GradientButton, ButtonGroup } from '@/components/GradientButton';
import { PrimitiveCard, PrimitiveGrid } from '@/components/PrimitiveCard';

export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    HeroScene,
    Badge,
    FeatureCard,
    FeatureGrid,
    GradientButton,
    ButtonGroup,
    PrimitiveCard,
    PrimitiveGrid,
    ...components,
  };
}
```

## Landing Page Structure

Example structure for a polished introduction page:

```mdx
---
title: Introduction
description: Atomic building blocks for AI coding systems
---

<HeroScene />

<div className="flex flex-wrap items-center gap-2 mb-6">
  <Badge variant="indigo" icon="bot">AI-Native</Badge>
  <Badge variant="purple" icon="package">Version Controlled</Badge>
  <Badge variant="pink" icon="plug">Provider Agnostic</Badge>
  <Badge variant="cyan" icon="zap">Open Source</Badge>
</div>

## What is [Project Name]?

Brief description...

<ButtonGroup>
  <GradientButton href="/docs/quickstart" variant="bright" icon="rocket">
    Get Started
  </GradientButton>
  <GradientButton href="/docs/cli" variant="outline" icon="terminal">
    CLI Reference
  </GradientButton>
</ButtonGroup>

## Key Features

<FeatureGrid>
  <FeatureCard icon="lock" title="Version Control" description="..." gradient="purple" />
  <FeatureCard icon="plug" title="Provider Agnostic" description="..." gradient="indigo" />
  <FeatureCard icon="check" title="Strict Validation" description="..." gradient="cyan" />
  <FeatureCard icon="puzzle" title="Composable" description="..." gradient="pink" />
</FeatureGrid>
```

## Icon Usage Guidelines

Use Lucide React icons throughout:

| Context | Icon | Usage |
|---------|------|-------|
| Navigation | `BookOpen` | Documentation |
| Navigation | `Terminal` | CLI Reference |
| Navigation | `Wrench` | Maintaining |
| Feature | `Lock` | Security/Version Control |
| Feature | `Plug` | Integration |
| Feature | `Shield` | Protection |
| Feature | `Zap` | Speed/Performance |
| Primitive | `Bot` | Agent |
| Primitive | `Zap` | Command |
| Primitive | `Brain` | Skill |
| Primitive | `Wrench` | Tool |
| Primitive | `Anchor` | Hook |

## Best Practices

1. **Always use theme-aware colors** - Support both light and dark modes
2. **Use semantic color variants** - Match colors to meaning (indigo=primary, purple=secondary)
3. **Maintain hover states** - All interactive elements should have hover feedback
4. **Keep text readable** - Use darker colors on light backgrounds (700 vs 400)
5. **Group related CTAs** - Use ButtonGroup for multiple buttons
6. **Use grids for features** - FeatureGrid/PrimitiveGrid maintain consistent spacing

## Recommended File Structure

```
<project-root>/
├── app/
│   ├── (home)/
│   │   ├── layout.tsx      # Home layout with navbar
│   │   └── page.tsx        # Landing page with HeroScene
│   ├── docs/
│   │   └── layout.tsx      # Docs layout with sidebar
│   ├── global.css          # Custom CSS enhancements
│   └── layout.tsx          # Root layout with metadata
├── components/
│   ├── Badge.tsx
│   ├── FeatureCard.tsx
│   ├── GradientButton.tsx
│   ├── HeroScene.tsx
│   └── PrimitiveCard.tsx
├── content/
│   └── docs/
│       └── index.mdx       # Introduction page
├── lib/
│   ├── cn.ts               # Class name utility
│   ├── layout.shared.tsx   # Shared layout config (nav, logo)
│   └── source.ts           # Content source loaders
├── public/
│   ├── favicon.svg         # Site favicon
│   ├── logo-dark.svg       # Dark mode logo
│   └── logo-light.svg      # Light mode logo
└── mdx-components.tsx      # MDX component registration
```

## GitHub Pages Deployment

### Static Export Configuration

For GitHub Pages deployment, configure `next.config.mjs` to use static export:

```javascript
// next.config.mjs
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
const isStaticExport = basePath.length > 0;

const config = {
  reactStrictMode: true,
  ...(isStaticExport && {
    output: 'export',
    basePath,
    images: { unoptimized: true },
  }),
};
```

### Static Asset Paths (CRITICAL)

**All static assets (images, favicon, logo) must use the basePath prefix for GitHub Pages:**

```typescript
// lib/layout.shared.tsx
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

// Logo images
<Image src={`${basePath}/logo-dark.svg`} ... />
<Image src={`${basePath}/logo-light.svg`} ... />
```

```typescript
// app/layout.tsx
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

export const metadata: Metadata = {
  icons: {
    icon: `${basePath}/favicon.svg`,
    apple: `${basePath}/favicon.svg`,
  },
  metadataBase: new URL('https://yourorg.github.io/repo-name'),
};
```

### Search API for Static Export

The search API must use `staticGET` for static export:

```typescript
// app/api/search/route.ts
import { createSearchAPI } from 'fumadocs-core/search/server';

export const revalidate = 3600;

export const { staticGET: GET } = createSearchAPI('advanced', {
  indexes: source.getPages().map((page) => ({
    title: page.data.title,
    description: page.data.description,
    url: page.url,
    id: page.url,
    structuredData: page.data.structuredData,
  })),
});
```

### GitHub Actions Workflow

```yaml
# .github/workflows/docs.yml
name: Deploy Docs

on:
  push:
    branches: [main]
    paths:
      - 'docs/**'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: docs/package-lock.json
      - run: npm ci
        working-directory: ./docs
      - run: npm run build
        working-directory: ./docs
        env:
          NEXT_PUBLIC_BASE_PATH: /repo-name
      - uses: actions/upload-pages-artifact@v3
        with:
          path: ./docs/out

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/deploy-pages@v4
        id: deployment
```

### GitHub Settings

1. Go to **Settings → Pages**
2. Set **Source** to **GitHub Actions**
3. The workflow will deploy automatically on push to main

## Search Configuration

For static export, search must be configured to use the correct API endpoint with basePath:

### RootProvider Search Configuration

For static export, use `type: 'static'` which downloads the search index once and searches client-side:

```typescript
// app/layout.tsx
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

<RootProvider
  theme={{
    defaultTheme: 'dark',
    attribute: 'class',
    enableSystem: true,
  }}
  search={{
    options: {
      type: 'static',  // Required for static export
      api: `${basePath}/api/search`,
    },
  }}
>
  {children}
</RootProvider>
```

**Key points:**
- `type: 'static'` tells Fumadocs to download the search index and search locally using Orama
- `api` must include the basePath for GitHub Pages
- The search route should use `staticGET` which exports the index, not search results

## LLM-Friendly Documentation

Fumadocs supports generating plain text exports for LLMs via route handlers.

### Full Text Export Route

```typescript
// app/llms-full.txt/route.ts
import { source } from '@/lib/source';
import { NextResponse } from 'next/server';

export const revalidate = 3600;

export function GET() {
  const pages = source.getPages();
  
  const content = pages
    .map((page) => {
      return `# ${page.data.title}\n\n${page.data.description || ''}\n\nURL: ${page.url}\n\n---\n`;
    })
    .join('\n');

  return new NextResponse(content, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
```

Access at: `https://your-site.github.io/repo-name/llms-full.txt`

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Logo/favicon not loading | Add `basePath` prefix to asset paths in layout.tsx and layout.shared.tsx |
| Search not working | Configure `search.options.api` with basePath in RootProvider |
| Search API fails on static export | Use `staticGET` instead of `GET` in route handler |
| Dynamic export error | Add `export const dynamic = 'force-static'` |
| Images broken | Set `images: { unoptimized: true }` in next.config.mjs |
| Links broken | Next.js handles internal links automatically with basePath |
| Three.js not rendering | Ensure `'use client'` directive and proper Canvas setup |
| Theme not detected | Use MutationObserver to watch `document.documentElement.classList` |

## Checklist for New Fumadocs Sites

- [ ] Configure `next.config.mjs` with basePath and static export
- [ ] Add basePath to logo images in `layout.shared.tsx`
- [ ] Add basePath to favicon in `app/layout.tsx`
- [ ] Configure search API endpoint with basePath in RootProvider
- [ ] Use `staticGET` for search API route
- [ ] Set up GitHub Actions workflow with `NEXT_PUBLIC_BASE_PATH`
- [ ] Enable GitHub Pages with "GitHub Actions" source
- [ ] Add Three.js hero scene (optional)
- [ ] Register custom components in `mdx-components.tsx`
- [ ] Add LLM-friendly text export route (optional)
