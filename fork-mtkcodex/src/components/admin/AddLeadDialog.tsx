'use client';

import { useState } from 'react';
import { RefreshCw, UserPlus } from 'lucide-react';
import type { Lead, LeadStatus } from '@/lib/lead-types';
import { leadsApi } from '@/components/admin/client-api';
import { Field, Modal, buttonClass, inputClass, primaryButtonClass, textareaClass } from '@/components/admin/ui';

export default function AddLeadDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (lead: Lead) => void }) {
  const [form, setForm] = useState({
    name: '',
    phone: '',
    email: '',
    business_type: '',
    area: '',
    status: 'new' as LeadStatus,
    note: '',
    starred: false,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const lead = await leadsApi.create({
        name: form.name,
        phone: form.phone,
        email: form.email,
        business_type: form.business_type,
        area: form.area,
        status: form.status,
        starred: form.starred,
        append_note: form.note,
      });
      onCreated(lead);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add the lead');
      setBusy(false);
    }
  }

  return (
    <Modal title="Add a lead" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4 p-5">
        <Field label="Business name *">
          <input required value={form.name} onChange={(e) => set('name', e.target.value)} className={inputClass} autoFocus />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Phone / WhatsApp" hint="0300… or +92300…">
            <input value={form.phone} onChange={(e) => set('phone', e.target.value)} className={inputClass} inputMode="tel" />
          </Field>
          <Field label="Email">
            <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} className={inputClass} />
          </Field>
          <Field label="Business type">
            <input value={form.business_type} onChange={(e) => set('business_type', e.target.value)} className={inputClass} />
          </Field>
          <Field label="Area">
            <input value={form.area} onChange={(e) => set('area', e.target.value)} className={inputClass} />
          </Field>
          <Field label="Status">
            <select value={form.status} onChange={(e) => set('status', e.target.value as LeadStatus)} className={inputClass}>
              <option value="new">New</option>
              <option value="queued">Queued for outreach</option>
              <option value="replied">Replied</option>
              <option value="interested">Interested</option>
            </select>
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input type="checkbox" checked={form.starred} onChange={(e) => set('starred', e.target.checked)} /> Important (star)
          </label>
        </div>
        <Field label="Note">
          <textarea rows={3} value={form.note} onChange={(e) => set('note', e.target.value)} className={textareaClass} />
        </Field>
        {error && <p className="text-sm text-red-500">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={buttonClass}>
            Cancel
          </button>
          <button type="submit" disabled={busy || !form.name.trim() || (!form.phone.trim() && !form.email.trim())} className={primaryButtonClass}>
            {busy ? <RefreshCw className="size-4 animate-spin" /> : <UserPlus className="size-4" />} Add lead
          </button>
        </div>
      </form>
    </Modal>
  );
}
