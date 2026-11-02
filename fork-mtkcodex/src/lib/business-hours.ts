import { site } from '@/data/site';

/**
 * Office hours in Lahore (site.openingHours), expressed for any visitor's
 * timezone. Client-safe: used by the chat widget and the server auto-reply.
 */

const OFFICE_TZ = site.timezone;
const [OPEN_H, OPEN_M] = site.openingHours.opens.split(':').map(Number);
const [CLOSE_H, CLOSE_M] = site.openingHours.closes.split(':').map(Number);
const OPEN_DAYS = new Set<string>(site.openingHours.days);

/** Weekday name and minutes since midnight in the office timezone. */
function officeClock(date: Date) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: OFFICE_TZ,
    weekday: 'long',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value || '';
  return { day: get('weekday'), minutes: Number(get('hour')) * 60 + Number(get('minute')) };
}

export function officeOpen(date: Date = new Date()): boolean {
  const { day, minutes } = officeClock(date);
  return OPEN_DAYS.has(day) && minutes >= OPEN_H * 60 + OPEN_M && minutes < CLOSE_H * 60 + CLOSE_M;
}

/** The next moment the office opens (now if it is open), to the nearest 15 minutes. */
export function nextOpening(from: Date = new Date()): Date {
  if (officeOpen(from)) return from;
  // Walk forward in 15-minute steps; a week is at most 672 steps.
  const step = 15 * 60 * 1000;
  let t = Math.ceil(from.getTime() / step) * step;
  for (let i = 0; i < 700; i++, t += step) {
    if (officeOpen(new Date(t))) return new Date(t);
  }
  return from;
}

/** "Mon 10:00 AM" in the visitor's timezone (falls back to Lahore time). */
export function formatInZone(date: Date, timezone?: string): string {
  const options: Intl.DateTimeFormatOptions = { weekday: 'short', hour: 'numeric', minute: '2-digit' };
  try {
    return new Intl.DateTimeFormat('en-US', { ...options, timeZone: timezone || OFFICE_TZ }).format(date);
  } catch {
    return new Intl.DateTimeFormat('en-US', { ...options, timeZone: OFFICE_TZ }).format(date);
  }
}

/** One or two sentences for an offline visitor, in their own time. */
export function offlineNotice(timezone?: string, options: { email?: string; now?: Date } = {}): string {
  const now = options.now ?? new Date();
  const opens = nextOpening(now);
  const lahore = new Intl.DateTimeFormat('en-US', { timeZone: OFFICE_TZ, hour: 'numeric', minute: '2-digit' }).format(now);
  const back = `Our team is offline right now (it's ${lahore} in Lahore). We're back ${formatInZone(opens, timezone)} your time.`;
  return options.email
    ? `Thanks! ${back} We'll also reply to ${options.email}.`
    : `${back} Leave your email and we'll reply there too.`;
}

