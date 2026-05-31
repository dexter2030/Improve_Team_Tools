"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import Link from "next/link";
import { bulkImportAction, type BulkImportResult } from "../actions";

export function ImportForm({ example }: { example: string }) {
  const [text, setText] = useState("");
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<BulkImportResult | null>(null);

  function submit() {
    if (!text.trim()) {
      toast.error("Paste data first");
      return;
    }
    startTransition(async () => {
      const r = await bulkImportAction(text);
      setResult(r);
      if (r.added > 0) {
        toast.success(`Added ${r.added} of ${r.parsed} profiles`);
      } else {
        toast.error("Nothing added — check results below");
      }
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button onClick={submit} disabled={pending}>
          {pending ? "Importing..." : "Import"}
        </Button>
        <Button
          variant="outline"
          onClick={() => setText(example)}
          disabled={pending}
          size="sm"
        >
          Insert example
        </Button>
        {text && !pending && (
          <span className="text-xs text-muted-foreground">
            {text.split(/\r?\n/).filter(Boolean).length - 1} data rows
          </span>
        )}
      </div>

      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={12}
        placeholder="Paste CSV/TSV with header here..."
        className="font-mono text-xs"
        disabled={pending}
      />

      {result && (
        <div className="rounded-lg border bg-card p-4 space-y-3">
          <div className="flex items-center gap-4 text-sm">
            <span>
              <Badge>{result.added} added</Badge>
            </span>
            {result.failed > 0 && (
              <span>
                <Badge variant="destructive">{result.failed} errors</Badge>
              </span>
            )}
            <span className="text-muted-foreground">
              of {result.parsed} parsed rows
            </span>
          </div>

          <div className="border rounded">
            <table className="w-full text-xs">
              <thead className="border-b bg-muted/40">
                <tr className="text-left text-muted-foreground">
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Result</th>
                  <th className="px-3 py-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((r, i) => (
                  <tr key={i} className="border-b last:border-b-0">
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">
                      {r.row}
                    </td>
                    <td className="px-3 py-2 font-medium">
                      {r.profileId ? (
                        <Link
                          href={`/scouting/${r.profileId}`}
                          className="text-primary hover:underline"
                        >
                          {r.displayName || "—"}
                        </Link>
                      ) : (
                        r.displayName || "—"
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {r.ok ? (
                        <Badge>{r.resolutionState ?? "ok"}</Badge>
                      ) : (
                        <Badge variant="destructive">error</Badge>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.errors?.join("; ") ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
