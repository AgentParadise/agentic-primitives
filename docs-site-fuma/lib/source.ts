import { docs, cli, maintaining } from 'fumadocs-mdx:collections/server';
import { type InferPageType, loader } from 'fumadocs-core/source';
import type { Root, Folder } from 'fumadocs-core/page-tree';

// Main docs source
export const source = loader({
  baseUrl: '/docs',
  source: docs.toFumadocsSource(),
});

// CLI Reference source
export const cliSource = loader({
  baseUrl: '/docs/cli',
  source: cli.toFumadocsSource(),
});

// Maintaining Docs source
export const maintainingSource = loader({
  baseUrl: '/docs/maintaining',
  source: maintaining.toFumadocsSource(),
});

// Combined page tree with all sections as root folders
export function getCombinedTree(): Root {
  return {
    name: 'Docs',
    children: [
      // Documentation section (root folder)
      {
        type: 'folder',
        name: 'Documentation',
        root: true,
        index: {
          type: 'page',
          name: 'Introduction',
          url: '/docs',
        },
        children: source.pageTree.children,
      } as Folder,
      // CLI Reference section (root folder)
      {
        type: 'folder',
        name: 'CLI Reference',
        root: true,
        index: {
          type: 'page',
          name: 'Overview',
          url: '/docs/cli',
        },
        children: cliSource.pageTree.children,
      } as Folder,
      // Maintaining section (root folder)
      {
        type: 'folder',
        name: 'Maintaining',
        root: true,
        index: {
          type: 'page',
          name: 'Overview',
          url: '/docs/maintaining',
        },
        children: maintainingSource.pageTree.children,
      } as Folder,
    ],
  };
}

// Get page from the appropriate source based on slug
export function getPage(slugs: string[] | undefined) {
  if (!slugs || slugs.length === 0) {
    return source.getPage([]);
  }

  const [first, ...rest] = slugs;

  if (first === 'cli') {
    return cliSource.getPage(rest);
  }

  if (first === 'maintaining') {
    return maintainingSource.getPage(rest);
  }

  return source.getPage(slugs);
}

// Generate all static params
export function generateAllParams() {
  return [
    ...source.generateParams(),
    ...cliSource.generateParams().map((p) => ({ slug: ['cli', ...(p.slug || [])] })),
    ...maintainingSource.generateParams().map((p) => ({ slug: ['maintaining', ...(p.slug || [])] })),
  ];
}

export function getPageImage(page: InferPageType<typeof source>) {
  const segments = [...page.slugs, 'image.png'];

  return {
    segments,
    url: `/og/docs/${segments.join('/')}`,
  };
}

export async function getLLMText(page: InferPageType<typeof source>) {
  const processed = await page.data.getText('processed');

  return `# ${page.data.title}

${processed}`;
}
