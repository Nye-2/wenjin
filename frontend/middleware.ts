import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_STORAGE_KEY = "auth-storage";

const PUBLIC_PATHS = [
  "/",
  "/login",
  "/register",
  "/api/auth",
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
}

function readAuthCookie(rawValue?: string): { state?: { isAuthenticated?: boolean } } | null {
  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(decodeURIComponent(rawValue));
  } catch {
    try {
      return JSON.parse(rawValue);
    } catch {
      return null;
    }
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip static files, Next.js internals, and API routes
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".") // static assets
  ) {
    return NextResponse.next();
  }

  // Allow public paths
  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  // Read auth state from cookie or localStorage (via request headers)
  // Note: localStorage is not accessible server-side, so we check a cookie
  // or rely on the client-side redirect as fallback.
  // For server-side protection, we use the auth-storage cookie approach.
  const authCookie = request.cookies.get(AUTH_STORAGE_KEY)?.value;

  if (!authCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  const parsed = readAuthCookie(authCookie);
  const isAuthenticated = parsed?.state?.isAuthenticated === true;

  if (!isAuthenticated) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
