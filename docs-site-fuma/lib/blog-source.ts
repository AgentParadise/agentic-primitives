import { blog } from 'fumadocs-mdx:collections/server';
import { loader } from 'fumadocs-core/source';

export const blogSource = loader({
  baseUrl: '/blog',
  source: blog.toFumadocsSource(),
});

export function getBlogPosts() {
  return blogSource.getPages().sort((a, b) => {
    const dateA = new Date(a.data.date || 0);
    const dateB = new Date(b.data.date || 0);
    return dateB.getTime() - dateA.getTime();
  });
}
