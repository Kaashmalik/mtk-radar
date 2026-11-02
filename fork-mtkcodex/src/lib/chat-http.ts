import { NextResponse } from 'next/server';
import { LeadError } from '@/lib/leads';
import { chatSessionByToken, type ChatSession } from '@/lib/chat';

/** Shared bits for the public /api/chat/* routes. */

export const noStore = { 'Cache-Control': 'no-store' };

export function chatError(error: unknown, fallback: string) {
  if (error instanceof LeadError) return NextResponse.json({ error: error.message }, { status: error.status, headers: noStore });
  console.error(`chat: ${fallback}`, error instanceof Error ? error.message : error);
  return NextResponse.json({ error: fallback }, { status: 500, headers: noStore });
}

export async function readJson(req: Request): Promise<Record<string, unknown> | null> {
  try {
    const body = await req.json();
    return body && typeof body === 'object' && !Array.isArray(body) ? (body as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** The visitor token travels in a header so it never lands in URLs or logs. */
export async function sessionFromRequest(req: Request, body?: Record<string, unknown> | null): Promise<ChatSession | null> {
  return chatSessionByToken(req.headers.get('x-chat-token') || body?.token);
}

export const text = (value: unknown, max: number) => (typeof value === 'string' ? value.trim().slice(0, max) : '');
