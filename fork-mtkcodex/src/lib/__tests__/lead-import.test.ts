import { describe, expect, it } from 'vitest';
import { autoMapColumns, googleSheetCsvUrl, parseDelimited, rowToLead } from '@/lib/lead-import';

describe('parseDelimited', () => {
  it('parses quoted CSV with commas, quotes and newlines', () => {
    const rows = parseDelimited('﻿name,notes\r\n"Acme, Inc","said ""hi""\nthen left"\r\n');
    expect(rows).toEqual([{ name: 'Acme, Inc', notes: 'said "hi"\nthen left' }]);
  });
  it('detects tab-separated files', () => {
    expect(parseDelimited('name\tphone\nAcme\t0300 1234567\n')).toEqual([{ name: 'Acme', phone: '0300 1234567' }]);
  });
});

describe('autoMapColumns', () => {
  it('matches scraper and sheet headers', () => {
    const mapping = autoMapColumns(['lead_id', 'Business Name', 'phone_e164', 'Google Rating', 'Lead Score']);
    expect(mapping).toMatchObject({
      id: 'lead_id',
      name: 'Business Name',
      phone: 'phone_e164',
      rating: 'Google Rating',
      lead_score: 'Lead Score',
    });
  });
});

describe('rowToLead', () => {
  const mapping = { name: 'name', phone: 'phone', status: 'status', next_followup: 'f', tags: 'tags', lead_score: 's' };
  it('normalises fields', () => {
    const result = rowToLead(
      { name: 'Acme', phone: '0300 1234567', status: 'Sent', f: '05/11/2026', tags: 'Hot; Dental', s: '120' },
      mapping,
    );
    expect(result.lead).toMatchObject({
      name: 'Acme',
      phone: '+923001234567',
      status: 'contacted',
      next_followup: '2026-11-05',
      tags: ['hot', 'dental'],
      lead_score: 100,
    });
  });
  it('rejects rows without a name or contact', () => {
    expect(rowToLead({ name: '', phone: '0300 1234567' }, mapping).error).toBeTruthy();
    expect(rowToLead({ name: 'Acme', phone: 'n/a' }, mapping).error).toBeTruthy();
  });
});

describe('googleSheetCsvUrl', () => {
  it('builds the CSV export URL with the tab gid', () => {
    expect(googleSheetCsvUrl('https://docs.google.com/spreadsheets/d/1DFO45PtJIEDnGX-xyCbzp1FTGXDVVok/edit#gid=312869384')).toBe(
      'https://docs.google.com/spreadsheets/d/1DFO45PtJIEDnGX-xyCbzp1FTGXDVVok/export?format=csv&gid=312869384',
    );
  });
  it('refuses other hosts and plain http', () => {
    expect(googleSheetCsvUrl('https://evil.example/spreadsheets/d/1DFO45PtJIEDnGX-xyCbzp1FTGXDVVok')).toBeNull();
    expect(googleSheetCsvUrl('http://docs.google.com/spreadsheets/d/1DFO45PtJIEDnGX-xyCbzp1FTGXDVVok')).toBeNull();
  });
});
