"use client";

import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { deleteProfileAction } from "../actions";

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

  return (
    <Button
      variant="destructive"
      size="sm"
      onClick={onDelete}
      disabled={pending}
    >
      <Trash2 className="h-4 w-4 mr-1" />
      {pending ? "Usuwam..." : "Usuń"}
    </Button>
  );
}
