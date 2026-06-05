import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const AUTH_STORAGE_KEY = "auth-storage";

const PUBLIC_PATHS = [
  "/",
  "/docs",
  "/login",
  "/pricing",
  "/register",
  "/api/auth",
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
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

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

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
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
