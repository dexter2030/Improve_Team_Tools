"use client";

import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Download, RefreshCw } from "lucide-react";
import { syncLeaguePlayersAction } from "./actions";

export function LeagueSyncButton({
  league,
  hasData,
}: {
  league: string;
  hasData: boolean;
}) {
  const [pending, startTransition] = useTransition();

  function sync() {
    startTransition(async () => {
      const r = await syncLeaguePlayersAction(league);
      if (r.error) toast.error(`${league}: ${r.error}`);
      else toast.success(`${league}: ${r.saved} players saved`);
    });
  }

  return (
    <Button
      onClick={sync}
      disabled={pending}
      size="sm"
      variant={hasData ? "outline" : "default"}
    >
      {pending ? (
        "..."
      ) : hasData ? (
        <>
          <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
        </>
      ) : (
        <>
          <Download className="h-3.5 w-3.5 mr-1" /> Fetch
        </>
      )}
    </Button>
  );
}
