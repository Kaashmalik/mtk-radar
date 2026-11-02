import { NextResponse } from 'next/server';
import { agentName } from '@/lib/chat';
import { storageMode } from '@/lib/leads';
import { adminOnline } from '@/lib/notify';
import { officeOpen } from '@/lib/business-hours';

export const dynamic = 'force-dynamic';

/** Whether live chat is available and the team is around, for the widget header. */
export async function GET() {
  const enabled = storageMode() !== 'readonly';
  return NextResponse.json(
    { enabled, agent: { name: agentName(), online: enabled ? await adminOnline() : false }, officeOpen: officeOpen() },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
