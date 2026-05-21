"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { updateNotesAction } from "../actions";

export function NotesEditor({ id, initial }: { id: string; initial: string }) {
  const [value, setValue] = useState(initial);
  const [pending, startTransition] = useTransition();
  const dirty = value !== initial;

  function save() {
    startTransition(async () => {
      await updateNotesAction(id, value);
      toast.success("Notatka zapisana.");
    });
  }

  return (
    <div className="space-y-3">
      <Textarea
        rows={6}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Twoja ocena gracza..."
      />
      <Button onClick={save} disabled={!dirty || pending}>
        {pending ? "Zapisuję..." : "Zapisz notatkę"}
      </Button>
    </div>
  );
}
