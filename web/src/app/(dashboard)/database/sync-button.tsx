"use client";

import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Download, RefreshCw } from "lucide-react";
import { syncLeagueAction } from "./actions";

export function SyncButton({
  league,
  hasData,
}: {
  league: string;
  hasData: boolean;
}) {
  const [pending, startTransition] = useTransition();

  function sync() {
    startTransition(async () => {
      const result = await syncLeagueAction(league);
      if (result.error) {
        toast.error(`${league}: ${result.error}`);
      } else {
        toast.success(
          `${league}: pobrano ${result.fetched}, zapisano ${result.saved} draftów.`
        );
      }
    });
  }

  return (
    <Button onClick={sync} disabled={pending} size="sm" variant={hasData ? "outline" : "default"}>
      {pending ? (
        "Pobieram..."
      ) : hasData ? (
        <>
          <RefreshCw className="h-3.5 w-3.5 mr-1" />
          Odśwież
        </>
      ) : (
        <>
          <Download className="h-3.5 w-3.5 mr-1" />
          Wczytaj
        </>
      )}
    </Button>
  );
}
