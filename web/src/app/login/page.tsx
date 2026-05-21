import { redirect } from "next/navigation";
import { LoginForm } from "./login-form";
import { authEnabled } from "@/lib/auth/session";

interface Props {
  searchParams: Promise<{ from?: string; error?: string }>;
}

export default async function LoginPage({ searchParams }: Props) {
  // Auth wyłączony? Skip do dashboardu.
  if (!authEnabled()) redirect("/scouting");
  const sp = await searchParams;
  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30">
      <div className="w-full max-w-sm bg-card border rounded-xl shadow-sm p-8 space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-semibold">Improve Team Tools</h1>
          <p className="text-sm text-muted-foreground">
            Strona prywatna — podaj hasło żeby kontynuować.
          </p>
        </div>
        <LoginForm from={sp.from ?? "/scouting"} error={sp.error} />
      </div>
    </div>
  );
}
