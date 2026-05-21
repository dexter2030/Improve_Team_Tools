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
    if (!confirm("Na pewno usunąć ten profil? Operacja jest nieodwracalna.")) {
      return;
    }
    startTransition(async () => {
      try {
        await deleteProfileAction(id);
        toast.success("Profil usunięty.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Nie udało się usunąć.");
      }
    });
  }

  function onReResolve() {
    startTransition(async () => {
      const result = await reResolveAction(id);
      if (!result.ok) {
        toast.error(result.errors?.join(", ") ?? "Re-resolve nie powiodło się.");
        return;
      }
      const resolved = result.reports?.filter((r) => r.outcome === "resolved").length ?? 0;
      const total = result.reports?.length ?? 0;
      toast.success(`Odświeżone: ${resolved}/${total} źródeł.`);
    });
  }

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={onReResolve}
        disabled={pending}
        title="Odśwież dane z Riot + Leaguepedia"
      >
        <RefreshCw className={`h-4 w-4 mr-1 ${pending ? "animate-spin" : ""}`} />
        Odśwież
      </Button>
      <Link
        href={`/scouting/${id}/edit`}
        className={buttonVariants({ variant: "outline", size: "sm" })}
      >
        <Pencil className="h-4 w-4 mr-1" />
        Edytuj
      </Link>
      <Button
        variant="destructive"
        size="sm"
        onClick={onDelete}
        disabled={pending}
      >
        <Trash2 className="h-4 w-4 mr-1" />
        Usuń
      </Button>
    </div>
  );
}
