import { blogSource, getBlogPosts } from '@/lib/blog-source';
import { notFound } from 'next/navigation';
import { getMDXComponents } from '@/mdx-components';
import type { Metadata } from 'next';
import Link from 'next/link';

interface PageProps {
  params: Promise<{ slug?: string[] }>;
}

// Blog index component
function BlogIndex() {
  const posts = getBlogPosts();

  return (
    <main className="container py-12 max-w-4xl mx-auto">
      <h1 className="text-4xl font-bold mb-8">Blog</h1>
      <p className="text-lg text-fd-muted-foreground mb-12">
        Updates, tutorials, and insights about agentic-p.
      </p>

      <div className="grid gap-8">
        {posts.map((post) => (
          <article
            key={post.url}
            className="group border border-fd-border rounded-lg p-6 hover:border-fd-primary transition-colors"
          >
            <Link href={post.url} className="block">
              <h2 className="text-2xl font-semibold group-hover:text-fd-primary transition-colors">
                {post.data.title}
              </h2>
              {post.data.description && (
                <p className="mt-2 text-fd-muted-foreground">
                  {post.data.description}
                </p>
              )}
              <div className="mt-4 flex items-center gap-4 text-sm text-fd-muted-foreground">
                {post.data.date && (
                  <time dateTime={String(post.data.date)}>
                    {new Date(post.data.date).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </time>
                )}
                {post.data.author && <span>by {post.data.author}</span>}
              </div>
            </Link>
          </article>
        ))}
      </div>

      {posts.length === 0 && (
        <p className="text-fd-muted-foreground">No blog posts yet.</p>
      )}
    </main>
  );
}

// Blog post component
function BlogPost({ post }: { post: ReturnType<typeof blogSource.getPage> }) {
  if (!post) return null;

  const MDX = post.data.body;

  return (
    <main className="container py-12 max-w-3xl mx-auto">
      <article className="prose dark:prose-invert max-w-none">
        <header className="mb-8 not-prose">
          <h1 className="text-4xl font-bold mb-4">{post.data.title}</h1>
          {post.data.description && (
            <p className="text-xl text-fd-muted-foreground mb-4">
              {post.data.description}
            </p>
          )}
          <div className="flex items-center gap-4 text-sm text-fd-muted-foreground">
            {post.data.date && (
              <time dateTime={String(post.data.date)}>
                {new Date(post.data.date).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </time>
            )}
            {post.data.author && <span>by {post.data.author}</span>}
          </div>
        </header>
        <MDX components={getMDXComponents({})} />
      </article>
    </main>
  );
}

export default async function Page({ params }: PageProps) {
  const { slug } = await params;

  // No slug = blog index
  if (!slug || slug.length === 0) {
    return <BlogIndex />;
  }

  // Has slug = individual post
  const post = blogSource.getPage(slug);

  if (!post) {
    notFound();
  }

  return <BlogPost post={post} />;
}

export function generateStaticParams() {
  // Include empty slug for index page
  return [
    { slug: [] },
    ...blogSource.generateParams(),
  ];
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;

  // Index page
  if (!slug || slug.length === 0) {
    return {
      title: 'Blog',
      description: 'Updates, tutorials, and insights about agentic-p.',
    };
  }

  // Individual post
  const post = blogSource.getPage(slug);

  if (!post) {
    return {};
  }

  return {
    title: post.data.title,
    description: post.data.description,
  };
}
