import { describe, expect, it } from 'vitest';
import { csvCell, leadStats, leadsToCsv, normalizePhone, waWindowOpen } from '@/lib/lead-types';
import { makeLead } from './fixtures';


describe('normalizePhone', () => {
  it('adds +92 to local Pakistani numbers', () => {
    expect(normalizePhone('0300-1234567')).toBe('+923001234567');
    expect(normalizePhone('3001234567')).toBe('+923001234567');
  });
  it('keeps international numbers', () => {
    expect(normalizePhone('+1 (415) 555-0100')).toBe('+14155550100');
    expect(normalizePhone('0044 20 7946 0958')).toBe('+442079460958');
  });
  it('rejects junk', () => {
    expect(normalizePhone('12')).toBe('');
    expect(normalizePhone('')).toBe('');
  });
});

describe('csvCell', () => {
  it('neutralises spreadsheet formulas', () => {
    expect(csvCell('=HYPERLINK("x")')).toBe(`"'=HYPERLINK(""x"")"`);
    expect(csvCell('@SUM(A1)')).toBe("'@SUM(A1)");
    expect(csvCell('+cmd|')).toBe("'+cmd|");
  });
  it('leaves phone numbers and plain text alone', () => {
    expect(csvCell('+923001234567')).toBe('+923001234567');
    expect(csvCell('-5')).toBe('-5');
    expect(csvCell('Hello, world')).toBe('"Hello, world"');
  });
  it('joins arrays', () => {
    expect(csvCell(['hot', 'dental'])).toBe('hot; dental');
  });
});

describe('leadsToCsv', () => {
  it('includes first_contacted and a BOM', () => {
    const csv = leadsToCsv([makeLead({ first_contacted: '2026-11-02' })]);
    expect(csv.startsWith('﻿')).toBe(true);
    expect(csv.split('\r\n')[0]).toContain('first_contacted');
    expect(csv).toContain('2026-11-02');
  });
});

describe('leadStats', () => {
  it('excludes do-not-contact leads from due and queued', () => {
    const stats = leadStats([
      makeLead({ id: 'a', status: 'queued', do_not_contact: true }),
      makeLead({ id: 'b', status: 'queued' }),
      makeLead({ id: 'c', status: 'contacted', next_followup: '2000-01-01', do_not_contact: true }),
      makeLead({ id: 'd', status: 'replied' }),
    ]);
    expect(stats.queued).toBe(1);
    expect(stats.dueToday).toBe(0);
    expect(stats.replyRate).toBe(50);
  });
});

describe('waWindowOpen', () => {
  it('is open for 24 hours after the last inbound message', () => {
    const now = Date.parse('2026-11-02T12:00:00Z');
    expect(waWindowOpen('2026-11-01T13:00:00Z', now)).toBe(true);
    expect(waWindowOpen('2026-11-01T11:00:00Z', now)).toBe(false);
    expect(waWindowOpen(null, now)).toBe(false);
  });
});
