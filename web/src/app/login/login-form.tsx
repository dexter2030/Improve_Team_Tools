"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function LoginForm({ from, error }: { from: string; error?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [localError, setLocalError] = useState<string | null>(error ?? null);

  function onSubmit(formData: FormData) {
    setLocalError(null);
    const password = String(formData.get("password") ?? "");
    startTransition(async () => {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        router.push(from || "/scouting");
        router.refresh();
      } else {
        setLocalError("Wrong password");
      }
    });
  }

  return (
    <form action={onSubmit} className="space-y-4">
      <Input
        name="password"
        type="password"
        autoFocus
        placeholder="Password"
        required
      />
      {localError && (
        <p className="text-sm text-destructive">{localError}</p>
      )}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Signing in..." : "Sign in"}
      </Button>
    </form>
  );
}
