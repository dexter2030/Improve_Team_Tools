import { cookies } from "next/headers";
import {
  checkPassword,
  cookieOptions,
  getCookieName,
  mintToken,
} from "@/lib/auth/session";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { password?: string };
  const password = String(body.password ?? "");

  if (!checkPassword(password)) {
    return Response.json({ ok: false }, { status: 401 });
  }

  const jar = await cookies();
  jar.set(getCookieName(), mintToken(), cookieOptions());
  return Response.json({ ok: true });
}
