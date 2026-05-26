/**
 * Edge proxy — chroni cały dashboard za hasłem.
 *
 * Next.js 16 zmienił nazwę z `middleware.ts` na `proxy.ts` (z `middleware()`
 * na `proxy()`). Edge runtime nie ma `node:crypto`, więc weryfikujemy HMAC
 * przez WebCrypto API. Brak APP_PASSWORD w env = auth wyłączony.
 */

import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "ITT_AUTH";
const COOKIE_TTL_MS = 14 * 24 * 60 * 60 * 1000;

// Te ścieżki nie wymagają auth.
// /api/health/* zostawione publiczne — przydatne do uptime monitoring
// (Vercel/UptimeRobot/etc.) bez konieczności obsługiwania cookies.
// /api/cron/* ma własną auth przez `Authorization: Bearer ${CRON_SECRET}`,
// którą Vercel Cron ustawia automatycznie — cookie tu nie dotrze.
const PUBLIC_PATHS = [
  "/login",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/health",
  "/api/cron",
];

export async function proxy(req: NextRequest) {
  const password = process.env.APP_PASSWORD;
  if (!password) return NextResponse.next(); // auth wyłączony

  const { pathname } = req.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
    return NextResponse.next();
  }
  // Statyczne — zostaw (matcher już to wycina, ale defensywnie).
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon")
  ) {
    return NextResponse.next();
  }

  const token = req.cookies.get(COOKIE_NAME)?.value;
  const ok = token ? await verifyToken(token) : false;
  if (ok) return NextResponse.next();

  // Redirect na /login z `?from=` żeby po zalogowaniu wrócić.
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("from", pathname);
  return NextResponse.redirect(url);
}

async function verifyToken(token: string): Promise<boolean> {
  const secret = process.env.AUTH_SECRET;
  if (!secret || secret.length < 16) return false;

  const dot = token.indexOf(".");
  if (dot < 0) return false;
  const payload = token.slice(0, dot);
  const sig = token.slice(dot + 1);

  const expected = await hmacSha256(payload, secret);
  if (expected !== sig) return false;

  const issuedAt = Number(payload);
  if (!Number.isFinite(issuedAt)) return false;
  if (Date.now() - issuedAt > COOKIE_TTL_MS) return false;
  return true;
}

async function hmacSha256(payload: string, secret: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return base64url(new Uint8Array(sig));
}

function base64url(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

export const config = {
  matcher: [
    // Wszystko poza _next, favicons, plikami statycznymi
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
