"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global error]", error);
  }, [error]);

  return (
    <html lang="pl">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          padding: "2rem",
          maxWidth: "640px",
          margin: "4rem auto",
          color: "#1f2937",
        }}
      >
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>
          Improve Team Tools — błąd krytyczny
        </h1>
        <p style={{ marginTop: "1rem" }}>{error.message}</p>
        {error.digest && (
          <p style={{ fontSize: "0.75rem", opacity: 0.7, marginTop: "0.5rem" }}>
            Trace ID: <code>{error.digest}</code>
          </p>
        )}
        <button
          onClick={reset}
          style={{
            marginTop: "1rem",
            padding: "0.5rem 1rem",
            background: "#1f2937",
            color: "white",
            border: "none",
            borderRadius: "0.375rem",
            cursor: "pointer",
          }}
        >
          Spróbuj ponownie
        </button>
      </body>
    </html>
  );
}
