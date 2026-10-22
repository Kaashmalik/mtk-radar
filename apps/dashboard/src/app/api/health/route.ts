import { NextResponse } from "next/server";

/** Container liveness probe. Deliberately unauthenticated and side-effect
 * free: it proves the Next server is accepting requests, not that the API or
 * database is healthy (the dashboard renders those states explicitly). */
export function GET() {
  return NextResponse.json({ status: "ok", service: "dashboard" });
}
