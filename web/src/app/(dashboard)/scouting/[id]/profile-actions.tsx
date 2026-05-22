"use client";

import Link from "next/link";
import { useTransition } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { toast } from "sonner";
import { Trash2, RefreshCw, Pencil } from "lucide-react";
import { deleteProfileAction, reResolveAction } from "../actions";

export function ProfileActions({ id }: { id: string }) {
  const [pending, startTransition] = useTransition();

  function onDelete() {
    if (!confirm("Delete this profile? This cannot be undone.")) {
      return;
    }
    startTransition(async () => {
      try {
        await deleteProfileAction(id);
        toast.success("Profile deleted");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Delete failed");
      }
    });
  }

  function onReResolve() {
    startTransition(async () => {
      const result = await reResolveAction(id);
      if (!result.ok) {
        toast.error(result.errors?.join(", ") ?? "Refresh failed");
        return;
      }
      const resolved = result.reports?.filter((r) => r.outcome === "resolved").length ?? 0;
      const total = result.reports?.length ?? 0;
      toast.success(`Refreshed: ${resolved}/${total} sources`);
    });
  }

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={onReResolve}
        disabled={pending}
        title="Refresh data from Riot + Leaguepedia"
      >
        <RefreshCw className={`h-4 w-4 mr-1 ${pending ? "animate-spin" : ""}`} />
        Refresh
      </Button>
      <Link
        href={`/scouting/${id}/edit`}
        className={buttonVariants({ variant: "outline", size: "sm" })}
      >
        <Pencil className="h-4 w-4 mr-1" />
        Edit
      </Link>
      <Button
        variant="destructive"
        size="sm"
        onClick={onDelete}
        disabled={pending}
      >
        <Trash2 className="h-4 w-4 mr-1" />
        Delete
      </Button>
    </div>
  );
}
