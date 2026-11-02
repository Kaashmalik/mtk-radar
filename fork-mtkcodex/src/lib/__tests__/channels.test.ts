import { createHmac } from 'node:crypto';
import { afterEach, describe, expect, it } from 'vitest';
import { parseAddress, stripQuotedReply, tokenFromRecipients, verifyResendWebhook } from '@/lib/email';
import { nextOpening, offlineNotice, officeOpen } from '@/lib/business-hours';
import { geoFromRequest, isTimeZone } from '@/lib/geo';
import { localTime, placeLabel } from '@/lib/lead-types';

describe('verifyResendWebhook (Svix scheme)', () => {
  const secretBytes = Buffer.from('test-secret-key-0123456789');
  const secret = `whsec_${secretBytes.toString('base64')}`;
  const body = '{"type":"email.received","data":{"email_id":"abc"}}';
  const now = 1_793_500_000_000;
  const ts = String(Math.floor(now / 1000));
  const sig = createHmac('sha256', secretBytes).update(`msg_1.${ts}.${body}`).digest('base64');

  it('accepts a valid signature among several', () => {
    expect(verifyResendWebhook(body, { id: 'msg_1', timestamp: ts, signature: `v1,bogus v1,${sig}` }, secret, now)).toBe(true);
  });
  it('rejects a tampered body, wrong id or stale timestamp', () => {
    expect(verifyResendWebhook(`${body} `, { id: 'msg_1', timestamp: ts, signature: `v1,${sig}` }, secret, now)).toBe(false);
    expect(verifyResendWebhook(body, { id: 'msg_2', timestamp: ts, signature: `v1,${sig}` }, secret, now)).toBe(false);
    expect(verifyResendWebhook(body, { id: 'msg_1', timestamp: ts, signature: `v1,${sig}` }, secret, now + 10 * 60 * 1000)).toBe(false);
    expect(verifyResendWebhook(body, { id: null, timestamp: ts, signature: `v1,${sig}` }, secret, now)).toBe(false);
  });
});

describe('email helpers', () => {
  afterEach(() => {
    delete process.env.EMAIL_REPLY_DOMAIN;
  });

  it('parses display-name addresses', () => {
    expect(parseAddress('"Jane Doe" <Jane@Example.com>')).toEqual({ name: 'Jane Doe', email: 'jane@example.com' });
    expect(parseAddress('bob@example.com')).toEqual({ name: '', email: 'bob@example.com' });
  });

  it('finds the routing token on our reply domain only', () => {
    process.env.EMAIL_REPLY_DOMAIN = 'mtkcodex.tech';
    expect(tokenFromRecipients(['Kashif <r-abc123def456@mtkcodex.tech>'])).toBe('abc123def456');
    expect(tokenFromRecipients(['r-abc123def456@evil.example'])).toBeNull();
    expect(tokenFromRecipients(['hello@mtkcodex.tech'])).toBeNull();
  });

  it('strips quoted history from replies', () => {
    const reply = 'Yes, Tuesday works.\n\nOn Mon, 2 Nov 2026 at 10:00, Kashif <hello@mtkcodex.tech> wrote:\n> Would Tuesday work?';
    expect(stripQuotedReply(reply)).toBe('Yes, Tuesday works.');
    expect(stripQuotedReply('Sounds good\n> old line\nThanks')).toBe('Sounds good\nThanks');
  });
});

describe('business hours (Mon–Sat 10:00–19:00 Lahore)', () => {
  it('knows when the office is open', () => {
    expect(officeOpen(new Date('2026-11-02T06:00:00Z'))).toBe(true); // Mon 11:00 PKT
    expect(officeOpen(new Date('2026-11-02T15:00:00Z'))).toBe(false); // Mon 20:00 PKT
    expect(officeOpen(new Date('2026-11-08T06:00:00Z'))).toBe(false); // Sunday
  });
  it('finds the next opening and words it in the visitor timezone', () => {
    const saturdayNight = new Date('2026-11-07T16:00:00Z'); // Sat 21:00 PKT
    expect(nextOpening(saturdayNight).toISOString()).toBe('2026-11-09T05:00:00.000Z'); // Mon 10:00 PKT
    const notice = offlineNotice('America/New_York', { now: saturdayNight });
    expect(notice).toContain('Mon 12:00 AM');
    expect(notice).toContain('Leave your email');
    expect(offlineNotice('Europe/London', { now: saturdayNight, email: 'a@b.co' })).toContain('reply to a@b.co');
  });
});

describe('geo', () => {
  it('reads and rounds Vercel headers', () => {
    const req = new Request('https://x.test', {
      headers: {
        'x-vercel-ip-city': 'S%C3%A3o%20Paulo',
        'x-vercel-ip-country': 'br',
        'x-vercel-ip-country-region': 'sp',
        'x-vercel-ip-timezone': 'America/Sao_Paulo',
        'x-vercel-ip-latitude': '-23.5475',
        'x-vercel-ip-longitude': '-46.63611',
      },
    });
    expect(geoFromRequest(req)).toEqual({ city: 'São Paulo', region: 'SP', country: 'BR', timezone: 'America/Sao_Paulo', lat: -23.5, lng: -46.6 });
  });
  it('reads Netlify x-nf-geo (base64 JSON)', () => {
    const geo = Buffer.from(
      JSON.stringify({
        city: 'Lahore',
        country: { code: 'PK', name: 'Pakistan' },
        subdivision: { code: 'PB', name: 'Punjab' },
        timezone: 'Asia/Karachi',
        latitude: 31.5497,
        longitude: 74.3436,
      }),
    ).toString('base64');
    const req = new Request('https://x.test', { headers: { 'x-nf-geo': geo } });
    expect(geoFromRequest(req)).toEqual({ city: 'Lahore', region: 'PB', country: 'PK', timezone: 'Asia/Karachi', lat: 31.5, lng: 74.3 });
  });
  it('reads Cloudflare visitor-location headers and ignores unknown countries', () => {
    const req = new Request('https://x.test', {
      headers: { 'cf-ipcountry': 'US', 'cf-ipcity': 'Austin', 'cf-region-code': 'TX', 'cf-timezone': 'America/Chicago' },
    });
    expect(geoFromRequest(req)).toMatchObject({ city: 'Austin', region: 'TX', country: 'US', timezone: 'America/Chicago' });
    expect(geoFromRequest(new Request('https://x.test', { headers: { 'cf-ipcountry': 'XX' } })).country).toBe('');
    expect(geoFromRequest(new Request('https://x.test', { headers: { 'x-nf-geo': 'not-base64-json' } })).city).toBe('');
  });
  it('prefers the edge-provided client IP', async () => {
    const { clientIp } = await import('@/lib/rate-limit');
    const req = new Request('https://x.test', { headers: { 'x-forwarded-for': '10.0.0.1, 1.2.3.4', 'x-nf-client-connection-ip': '203.0.113.9' } });
    expect(clientIp(req)).toBe('203.0.113.9');
  });
  it('rejects junk timezones', () => {
    expect(isTimeZone('Asia/Karachi')).toBe(true);
    expect(isTimeZone('Mars/Olympus')).toBe(false);
    expect(isTimeZone('<script>')).toBe(false);
  });
  it('labels places with region and country names', () => {
    expect(placeLabel({ city: 'Lahore', region: 'PB', country: 'PK' })).toBe('Lahore, Punjab, Pakistan');
    expect(placeLabel({ city: 'Austin', region: 'TX', country: 'US' })).toBe('Austin, Texas, United States');
    expect(localTime('Bad/Zone')).toBe('');
  });
});
