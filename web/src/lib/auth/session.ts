/**
 * Signed session cookies — HMAC-SHA256, bez DB.
 *
 * Single-user single-password — nie potrzebujemy NextAuth ani sessions
 * w DB. Cookie zawiera timestamp + signature; middleware weryfikuje
 * signature i wiek. Logout = clear cookie.
 *
 * Cookie payload: `${issuedAtMs}.${signature}` (signature = base64url
 * HMAC-SHA256 issuedAtMs + secret).
 */

import "server-only";

import crypto from "node:crypto";

const COOKIE_NAME = "ITT_AUTH";
const COOKIE_TTL_MS = 14 * 24 * 60 * 60 * 1000; // 14 dni

export function getCookieName(): string {
  return COOKIE_NAME;
}

function getSecret(): string {
  const s = process.env.AUTH_SECRET;
  if (!s || s.length < 16) {
    throw new Error(
      "AUTH_SECRET is not set or too short (need >= 16 chars). Set it in env."
    );
  }
  return s;
}

function sign(payload: string): string {
  const secret = getSecret();
  return crypto
    .createHmac("sha256", secret)
    .update(payload)
    .digest("base64url");
}

/** Generuje wartość cookie dla teraz. */
export function mintToken(): string {
  const issuedAt = Date.now();
  const payload = String(issuedAt);
  return `${payload}.${sign(payload)}`;
}

/** Weryfikuje wartość cookie. Zwraca true jeśli OK i nieprzeterminowane. */
export function verifyToken(token: string | undefined | null): boolean {
  if (!token) return false;
  const dot = token.indexOf(".");
  if (dot < 0) return false;
  const payload = token.slice(0, dot);
  const sig = token.slice(dot + 1);

  const expected = sign(payload);
  // Constant-time compare
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  if (!crypto.timingSafeEqual(a, b)) return false;

  const issuedAt = Number(payload);
  if (!Number.isFinite(issuedAt)) return false;
  if (Date.now() - issuedAt > COOKIE_TTL_MS) return false;
  return true;
}

export function cookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: COOKIE_TTL_MS / 1000,
  };
}

/** Czy auth jest w ogóle skonfigurowany. Brak APP_PASSWORD = wyłączone. */
export function authEnabled(): boolean {
  return !!process.env.APP_PASSWORD;
}

export function checkPassword(input: string): boolean {
  const expected = process.env.APP_PASSWORD;
  if (!expected) return true; // auth wyłączony — daj zielone światło
  const a = Buffer.from(input);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}
