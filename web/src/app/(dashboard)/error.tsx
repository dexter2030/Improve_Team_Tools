"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Loguje do konsoli przeglądarki + Vercel runtime logs (jako client-side throw).
    console.error("[dashboard error]", error);
  }, [error]);

  return (
    <div className="max-w-2xl mx-auto py-12">
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Coś padło przy renderowaniu strony</AlertTitle>
        <AlertDescription className="space-y-3 mt-2">
          <p className="text-sm">{error.message || "Nieznany błąd serwera."}</p>
          {error.digest && (
            <p className="text-xs opacity-75">
              Trace ID:{" "}
              <code className="font-mono">{error.digest}</code> (Vercel
              Deployments → Runtime Logs)
            </p>
          )}
          <div className="flex gap-2 pt-2">
            <Button onClick={reset} size="sm">
              <RefreshCw className="h-3.5 w-3.5 mr-1" />
              Spróbuj ponownie
            </Button>
            <a
              href="/api/health"
              target="_blank"
              rel="noreferrer"
              className="text-xs underline self-center"
            >
              Sprawdź /api/health
            </a>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  );
}
