import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "nearshop_session";

/**
 * Fast redirect to sign-in for private areas when there is no session cookie at all.
 * This is a UX guard only; the API enforces authentication and roles on every request.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const url = new URL("/login", request.url);
  url.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/account/:path*", "/shop/:path*", "/admin/:path*"],
};
