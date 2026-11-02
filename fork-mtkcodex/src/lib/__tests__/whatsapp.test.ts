import { createHmac } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { isOptOut, parseWebhook, verifyWebhookSignature } from '@/lib/whatsapp';

describe('verifyWebhookSignature', () => {
  const body = '{"entry":[]}';
  const sig = `sha256=${createHmac('sha256', 'secret').update(body).digest('hex')}`;
  it('accepts a valid signature and rejects tampering', () => {
    expect(verifyWebhookSignature(body, sig, 'secret')).toBe(true);
    expect(verifyWebhookSignature(`${body} `, sig, 'secret')).toBe(false);
    expect(verifyWebhookSignature(body, null, 'secret')).toBe(false);
    expect(verifyWebhookSignature(body, 'sha256=abc', 'secret')).toBe(false);
  });
});

describe('parseWebhook', () => {
  it('extracts messages and statuses', () => {
    const parsed = parseWebhook({
      entry: [
        {
          changes: [
            {
              value: {
                contacts: [{ wa_id: '923001234567', profile: { name: 'Ali' } }],
                messages: [
                  { from: '923001234567', id: 'wamid.1', timestamp: '1793500000', type: 'text', text: { body: 'Yes please' } },
                ],
                statuses: [{ id: 'wamid.0', status: 'read', recipient_id: '923001234567' }],
              },
            },
          ],
        },
      ],
    });
    expect(parsed.messages[0]).toMatchObject({ from: '923001234567', profileName: 'Ali', body: 'Yes please' });
    expect(parsed.statuses[0]).toMatchObject({ wamid: 'wamid.0', status: 'read' });
  });
});

describe('isOptOut', () => {
  it('matches clear opt-outs only', () => {
    expect(isOptOut('STOP')).toBe(true);
    expect(isOptOut(' band karo ')).toBe(true);
    expect(isOptOut('Please do not stop, tell me more')).toBe(false);
  });
});
