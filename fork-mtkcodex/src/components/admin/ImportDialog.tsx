'use client';

import { useMemo, useState } from 'react';
import { CheckCircle2, FileSpreadsheet, Link2, RefreshCw, Upload } from 'lucide-react';
import {
  IMPORT_FIELDS,
  autoMapColumns,
  parseDelimited,
  rowToLead,
  type ColumnMapping,
  type ImportField,
  type RawRow,
} from '@/lib/lead-import';
import { importApi, type ImportSummary } from '@/components/admin/client-api';
import { Field, Modal, buttonClass, inputClass, primaryButtonClass } from '@/components/admin/ui';

// Small enough to finish well inside serverless time limits (10 s on Netlify).
const CHUNK = 200;

const FIELD_LABELS: Record<ImportField, string> = {
  id: 'Lead ID',
  name: 'Business name *',
  phone: 'Phone / WhatsApp *',
  email: 'Email',
  website: 'Website',
  business_type: 'Business type',
  area: 'Area / address',
  lead_score: 'Score',
  lead_tier: 'Tier',
  scenario: 'Scenario',
  rating: 'Google rating',
  reviews: 'Review count',
  google_maps_url: 'Google Maps URL',
  recommended_pitch: 'Pitch',
  message: 'WhatsApp message',
  status: 'Status',
  notes: 'Notes',
  tags: 'Tags',
  next_followup: 'Next follow-up',
  last_contacted: 'Last contacted',
  deal_stage: 'Deal stage',
  deal_value: 'Deal value',
};

export default function ImportDialog({ onClose, onImported }: { onClose: () => void; onImported: (summary: ImportSummary) => void }) {
  const [rows, setRows] = useState<RawRow[] | null>(null);
  const [sourceName, setSourceName] = useState('');
  const [mapping, setMapping] = useState<ColumnMapping>({});
  const [sheetUrl, setSheetUrl] = useState('');
  const [strategy, setStrategy] = useState<'skip' | 'merge'>('skip');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  const headers = useMemo(() => (rows?.[0] ? Object.keys(rows[0]) : []), [rows]);

  function load(parsed: RawRow[], name: string) {
    if (!parsed.length) {
      setError('No data rows found. The first row must be the column headers.');
      return;
    }
    setRows(parsed);
    setSourceName(name);
    setMapping(autoMapColumns(Object.keys(parsed[0])));
    setError('');
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    if (/\.xlsx?$/i.test(file.name)) {
      setError('Excel files: use File → Save As → CSV (or Google Sheets → Download → CSV), then upload the CSV.');
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setError('File is larger than 15 MB. Split it into smaller files.');
      return;
    }
    load(parseDelimited(await file.text()), file.name);
  }

  async function onSheet() {
    setBusy(true);
    setError('');
    try {
      const data = await importApi.sheet(sheetUrl);
      load(data.rows, 'Google Sheet');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read the sheet');
    } finally {
      setBusy(false);
    }
  }

  const checked = useMemo(() => {
    if (!rows) return null;
    let valid = 0;
    const problems = new Map<string, number>();
    const preview: ReturnType<typeof rowToLead>[] = [];
    for (const row of rows) {
      const result = rowToLead(row, mapping);
      if (result.lead) valid++;
      else problems.set(result.error, (problems.get(result.error) || 0) + 1);
      if (preview.length < 5) preview.push(result);
    }
    return { valid, problems: [...problems.entries()], preview };
  }, [rows, mapping]);

  const ready = Boolean(mapping.name && (mapping.phone || mapping.email) && checked?.valid);

  async function runImport() {
    if (!rows) return;
    setBusy(true);
    setError('');
    setProgress(0);
    const total: ImportSummary = { inserted: 0, updated: 0, skipped: 0, duplicates: 0, invalid: 0 };
    try {
      for (let i = 0; i < rows.length; i += CHUNK) {
        const result = await importApi.rows(rows.slice(i, i + CHUNK), mapping, strategy);
        for (const key of Object.keys(total) as (keyof ImportSummary)[]) total[key] += result[key] || 0;
        setProgress(Math.min(100, Math.round(((i + CHUNK) / rows.length) * 100)));
      }
      setSummary(total);
      onImported(total);
    } catch (err) {
      setError(
        `${err instanceof Error ? err.message : 'Import failed'}${total.inserted || total.updated ? ` (after ${total.inserted} added, ${total.updated} updated — re-running is safe)` : ''}`,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Import leads" onClose={onClose} wide>
      <div className="space-y-5 p-5">
        {summary ? (
          <div className="grid place-items-center gap-3 py-6 text-center">
            <CheckCircle2 className="size-10 text-emerald-500" />
            <p className="text-lg font-bold">Import complete</p>
            <p className="text-sm text-fg-muted">
              {summary.inserted} added · {summary.updated} updated · {summary.skipped} already in CRM ·{' '}
              {summary.duplicates} duplicate rows · {summary.invalid} invalid
            </p>
            <button onClick={onClose} className={primaryButtonClass}>
              Done
            </button>
          </div>
        ) : !rows ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="card flex cursor-pointer flex-col items-center gap-2 border-dashed p-6 text-center transition hover:border-brand">
                <Upload className="size-6 text-brand" />
                <span className="font-semibold">Upload CSV / TSV</span>
                <span className="text-xs text-fg-subtle">From Excel, Google Sheets or the scraper output</span>
                <input
                  type="file"
                  accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values"
                  className="sr-only"
                  onChange={(event) => onFile(event.target.files?.[0])}
                />
              </label>
              <div className="card flex flex-col gap-2 p-6">
                <span className="flex items-center gap-2 font-semibold">
                  <Link2 className="size-5 text-brand" /> Google Sheet link
                </span>
                <span className="text-xs text-fg-subtle">Share it as “Anyone with the link can view”. The open tab is used.</span>
                <input
                  value={sheetUrl}
                  onChange={(event) => setSheetUrl(event.target.value)}
                  placeholder="https://docs.google.com/spreadsheets/d/…"
                  className={inputClass}
                />
                <button onClick={onSheet} disabled={!sheetUrl.trim() || busy} className={buttonClass}>
                  {busy ? <RefreshCw className="size-4 animate-spin" /> : <FileSpreadsheet className="size-4" />} Load sheet
                </button>
              </div>
            </div>
            <p className="text-xs leading-relaxed text-fg-subtle">
              Columns are matched automatically (e.g. <code>name</code>, <code>phone_e164</code>, <code>area</code>,{' '}
              <code>lead_score</code>). Leads are de-duplicated by ID, phone and email, so importing the same file twice is
              safe. Local numbers like <code>0300…</code> are converted to <code>+92300…</code>.
            </p>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm">
                <strong>{rows.length}</strong> rows from {sourceName} ·{' '}
                <span className="text-emerald-600 dark:text-emerald-400">{checked?.valid} valid</span>
                {checked?.problems.map(([problem, count]) => (
                  <span key={problem} className="text-amber-600">
                    {' '}
                    · {count} × {problem.toLowerCase()}
                  </span>
                ))}
              </p>
              <button onClick={() => setRows(null)} className="text-xs font-semibold text-brand">
                Choose another file
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {(Object.keys(IMPORT_FIELDS) as ImportField[]).map((field) => (
                <Field key={field} label={FIELD_LABELS[field]}>
                  <select
                    value={mapping[field] || ''}
                    onChange={(event) => setMapping((current) => ({ ...current, [field]: event.target.value || undefined }))}
                    className={`${inputClass} ${mapping[field] ? 'border-brand/50' : ''}`}
                  >
                    <option value="">— not imported —</option>
                    {headers.map((header) => (
                      <option key={header} value={header}>
                        {header}
                      </option>
                    ))}
                  </select>
                </Field>
              ))}
            </div>

            <div className="overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[640px] text-left text-xs">
                <thead className="bg-muted/50 text-fg-subtle">
                  <tr>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">Phone</th>
                    <th className="px-3 py-2">Type · Area</th>
                    <th className="px-3 py-2">Score</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {checked?.preview.map((result, index) => (
                    <tr key={index} className="border-t border-line">
                      {result.lead ? (
                        <>
                          <td className="px-3 py-2 font-semibold">{result.lead.name}</td>
                          <td className="px-3 py-2 font-mono">{result.lead.phone || result.lead.email}</td>
                          <td className="px-3 py-2">{[result.lead.business_type, result.lead.area].filter(Boolean).join(' · ')}</td>
                          <td className="px-3 py-2">{result.lead.lead_score ?? '—'}</td>
                          <td className="px-3 py-2">{result.lead.status || 'new'}</td>
                        </>
                      ) : (
                        <td colSpan={5} className="px-3 py-2 text-amber-600">
                          Row {index + 1}: {result.error}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <fieldset className="grid gap-2 sm:grid-cols-2">
              <legend className="mb-2 text-xs font-semibold text-fg-muted">When a lead already exists</legend>
              {(
                [
                  ['skip', 'Skip it', 'Only add new leads. Existing ones are untouched.'],
                  ['merge', 'Refresh its profile', 'Update name, area, score, rating… Status, notes and history are kept.'],
                ] as const
              ).map(([value, title, text]) => (
                <label
                  key={value}
                  className={`flex cursor-pointer gap-3 rounded-xl border p-3 text-sm ${strategy === value ? 'border-brand bg-brand-soft/40' : 'border-line'}`}
                >
                  <input type="radio" name="strategy" checked={strategy === value} onChange={() => setStrategy(value)} />
                  <span>
                    <span className="font-semibold">{title}</span>
                    <span className="block text-xs text-fg-subtle">{text}</span>
                  </span>
                </label>
              ))}
            </fieldset>

            {busy && (
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-cta transition-all" style={{ width: `${progress}%` }} />
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button onClick={onClose} className={buttonClass}>
                Cancel
              </button>
              <button onClick={runImport} disabled={!ready || busy} className={primaryButtonClass}>
                {busy ? <RefreshCw className="size-4 animate-spin" /> : <Upload className="size-4" />}
                {busy ? `Importing… ${progress}%` : `Import ${checked?.valid || 0} leads`}
              </button>
            </div>
          </>
        )}
        {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-500">{error}</p>}
      </div>
    </Modal>
  );
}
