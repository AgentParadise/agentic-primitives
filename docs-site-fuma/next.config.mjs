import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

// Get basePath from environment variable (set in GitHub Actions workflow)
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
const isStaticExport = basePath.length > 0;

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Static export for GitHub Pages (when NEXT_PUBLIC_BASE_PATH is set)
  ...(isStaticExport && {
    output: 'export',
    basePath,
    images: {
      unoptimized: true,
    },
  }),
};

export default withMDX(config);
