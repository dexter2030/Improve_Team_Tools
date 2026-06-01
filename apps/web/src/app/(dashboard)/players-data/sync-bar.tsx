"use client";

import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Download, RefreshCw } from "lucide-react";
import { syncPlayersAction } from "./actions";

export function SyncBar({
  count,
  lastFetched,
}: {
  count: number;
  lastFetched: Date | null;
}) {
  const [pending, startTransition] = useTransition();

  function sync() {
    startTransition(async () => {
      const result = await syncPlayersAction();
      if (result.error) {
        toast.error(`Error: ${result.error}`);
      } else {
        toast.success(
          `Fetched ${result.fetched}, saved ${result.saved} players`
        );
      }
    });
  }

  return (
    <div className="flex items-center justify-between gap-4 p-4 rounded-lg border bg-muted/30">
      <div className="text-sm">
        <div className="font-medium">Global Leaguepedia player table</div>
        <div className="text-muted-foreground text-xs mt-0.5">
          {count > 0
            ? `${count.toLocaleString("en-US")} players in DB · last fetch: ${
                lastFetched
                  ? new Date(lastFetched).toLocaleString("en-US")
                  : "—"
              }`
            : "No data — fetch takes ~1-2 minutes (~30k players)."}
        </div>
      </div>
      <Button onClick={sync} disabled={pending} variant={count > 0 ? "outline" : "default"}>
        {pending ? (
          "Loading..."
        ) : count > 0 ? (
          <>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </>
        ) : (
          <>
            <Download className="h-4 w-4 mr-2" />
            Fetch
          </>
        )}
      </Button>
    </div>
  );
}
