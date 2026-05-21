import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getCookieName } from "@/lib/auth/session";

export async function POST() {
  const jar = await cookies();
  jar.delete(getCookieName());
  redirect("/login");
}

export async function GET() {
  const jar = await cookies();
  jar.delete(getCookieName());
  redirect("/login");
}
