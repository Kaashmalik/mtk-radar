import { describe, expect, it } from 'vitest';
import { LeadError, parseLeadPatch, planLeadChange } from '@/lib/leads';
import { makeLead } from './fixtures';

const base = makeLead({ id: 'l1', status: 'queued', notes: 'old', deal_stage: 'none' });

describe('planLeadChange', () => {
  it('logs a first send and stamps the date when marked contacted', () => {
    const { changes, activities } = planLeadChange(base, { status: 'contacted' }, '2026-11-02');
    expect(changes).toMatchObject({ status: 'contacted', last_contacted: '2026-11-02' });
    expect(activities.map((a) => a.kind)).toEqual(['status', 'message_out']);
  });

  it('refuses to queue a do-not-contact lead', () => {
    expect(() => planLeadChange({ ...base, status: 'lost', do_not_contact: true }, { status: 'queued' })).toThrow(LeadError);
    expect(() => planLeadChange(base, { do_not_contact: true })).toThrow(/do-not-contact/);
  });

  it('moves the status forward from the deal stage', () => {
    expect(planLeadChange({ ...base, status: 'replied' }, { deal_stage: 'proposal' }).changes.status).toBe('interested');
    expect(planLeadChange({ ...base, status: 'interested' }, { deal_stage: 'in_progress' }).changes.status).toBe('won');
  });

  it('appends dated notes', () => {
    const { changes, activities } = planLeadChange(base, { append_note: 'Called back' }, '2026-11-02');
    expect(changes.notes).toBe('old\n[2026-11-02] Called back');
    expect(activities[0]).toMatchObject({ kind: 'note', summary: 'Called back' });
  });
});

describe('parseLeadPatch', () => {
  it('validates types and normalises the phone', () => {
    expect(parseLeadPatch({ phone: '0300 1234567', tags: ['Hot', 'hot'] })).toEqual({ phone: '+923001234567', tags: ['hot'] });
    expect(() => parseLeadPatch({ status: 'bogus' })).toThrow(LeadError);
    expect(() => parseLeadPatch({ next_followup: 'tomorrow' })).toThrow(LeadError);
    expect(() => parseLeadPatch({ deal_value: -5 })).toThrow(LeadError);
  });
});
