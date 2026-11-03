import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

const PUBLIC_PATHS = ["/admin/login", "/account/login"];

/**
 * Refreshes the Supabase session cookie and sends signed-out visitors to the
 * right login page. This is an optimistic check only — every page and action
 * re-verifies the user and role on the server.
 */
export async function proxy(request: NextRequest) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return NextResponse.next(); // preview mode

  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        toSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });

  const { data } = await supabase.auth.getClaims();
  const path = request.nextUrl.pathname;
  if (data?.claims || PUBLIC_PATHS.some((p) => path.startsWith(p))) return response;

  const login = new URL(path.startsWith("/account") ? "/account/login" : "/admin/login", request.url);
  if (path.startsWith("/rider")) login.searchParams.set("next", "/rider");
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/admin/:path*", "/rider/:path*", "/account/:path*"],
};
