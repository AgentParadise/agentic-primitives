import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

// Check if building for GitHub Pages
const isGitHubPages = process.env.NEXT_PUBLIC_BASE_PATH === '/agentic-primitives';

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Static export for GitHub Pages
  ...(isGitHubPages && {
    output: 'export',
    basePath: '/agentic-primitives',
    images: {
      unoptimized: true,
    },
  }),
};

export default withMDX(config);
