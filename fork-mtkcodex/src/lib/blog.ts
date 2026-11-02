import fs from 'node:fs';
import path from 'node:path';
import { marked } from 'marked';

export interface Post {
  slug: string;
  title: string;
  date: string;
  summary: string;
  tags: string[];
  readingMinutes: number;
  body: string;
}

const dir = path.join(process.cwd(), 'content', 'blog');

function parse(file: string): Post {
  const raw = fs.readFileSync(path.join(dir, file), 'utf8').replace(/\r\n/g, '\n');
  const m = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  const meta: Record<string, string> = {};
  for (const line of (m?.[1] ?? '').split('\n')) {
    const i = line.indexOf(':');
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  const unquote = (v = '') => v.replace(/^"|"$/g, '');
  const body = m?.[2] ?? raw;
  let tags: string[] = [];
  try {
    tags = JSON.parse(meta.tags ?? '[]');
  } catch {}
  return {
    slug: file.replace(/\.md$/, ''),
    title: unquote(meta.title),
    date: unquote(meta.date),
    summary: unquote(meta.summary),
    tags,
    readingMinutes: Math.max(1, Math.round(body.split(/\s+/).length / 220)),
    body,
  };
}

export function getPosts(): Post[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.md'))
    .map(parse)
    .sort((a, b) => b.date.localeCompare(a.date));
}

export function getPost(slug: string) {
  return getPosts().find((p) => p.slug === slug);
}

// Content is authored by us (repo files), so rendering its HTML is safe.
export const renderMarkdown = (md: string) => marked.parse(md, { async: false }) as string;

export const formatDate = (d: string) =>
  new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
