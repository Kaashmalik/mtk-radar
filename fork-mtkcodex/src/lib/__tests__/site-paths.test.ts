import { describe, expect, it } from 'vitest';
import { trackablePath } from '@/lib/site-paths';

describe('trackablePath', () => {
  it('accepts real pages and strips queries', () => {
    expect(trackablePath('/')).toBe('/');
    expect(trackablePath('/pricing?ref=x')).toBe('/pricing');
    expect(trackablePath('/blog/choosing-a-crm-2026')).toBe('/blog/choosing-a-crm-2026');
  });
  it('rejects invented or private paths', () => {
    expect(trackablePath('/buy-cheap-pills')).toBe('');
    expect(trackablePath('/admin')).toBe('');
    expect(trackablePath('//evil.com')).toBe('');
    expect(trackablePath(42)).toBe('');
  });
});
