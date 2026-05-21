"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { editProfileAction } from "../../actions";
import type { Role, SourceReport } from "@/lib/profiles";

const ROLES: readonly Role[] = ["Top", "Jungle", "Mid", "Bot", "Support"];

export interface EditInitial {
  displayName: string;
  role: Role;
  age: number | null;
  nationality: string | null;
  lolprosUrl: string | null;
  opggUrls: string[];
  leaguepediaUrl: string;
}

export function EditPlayerForm({
  id,
  initial,
}: {
  id: string;
  initial: EditInitial;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [reports, setReports] = useState<SourceReport[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [role, setRole] = useState<Role>(initial.role);

  function onSubmit(formData: FormData) {
    setReports(null);
    setErrors([]);
    formData.set("role", role);
    startTransition(async () => {
      const result = await editProfileAction(id, formData);
      if (!result.ok) {
        setErrors(result.errors ?? ["Nieznany błąd."]);
        toast.error("Nie udało się zapisać.");
        return;
      }
      setReports(result.reports ?? []);
      toast.success("Profil zaktualizowany.");
      setTimeout(() => router.push(`/scouting/${id}`), 1500);
    });
  }

  return (
    <form action={onSubmit} className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="displayName">Nazwa gracza *</Label>
          <Input
            id="displayName"
            name="displayName"
            defaultValue={initial.displayName}
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="role">Rola *</Label>
          <Select value={role} onValueChange={(v) => setRole((v ?? "Mid") as Role)}>
            <SelectTrigger id="role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="age">Wiek</Label>
          <Input
            id="age"
            name="age"
            type="number"
            min={12}
            max={60}
            defaultValue={initial.age ?? ""}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="nationality">Kraj</Label>
          <Input
            id="nationality"
            name="nationality"
            defaultValue={initial.nationality ?? ""}
          />
        </div>

        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="leaguepediaUrl">Link Leaguepedia</Label>
          <Input
            id="leaguepediaUrl"
            name="leaguepediaUrl"
            defaultValue={initial.leaguepediaUrl}
          />
        </div>

        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="lolprosUrl">Link lolpros</Label>
          <Input
            id="lolprosUrl"
            name="lolprosUrl"
            defaultValue={initial.lolprosUrl ?? ""}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="opggUrls">Linki op.gg — jeden na linię</Label>
        <Textarea
          id="opggUrls"
          name="opggUrls"
          rows={4}
          defaultValue={initial.opggUrls.join("\n")}
        />
        <p className="text-xs text-muted-foreground">
          Niezmienione konta zachowają cached statystyki. Nowe pójdą do
          weryfikacji.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? "Zapisuję..." : "Zapisz zmiany"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => router.push(`/scouting/${id}`)}
          disabled={pending}
        >
          Anuluj
        </Button>
      </div>

      {errors.length > 0 && (
        <div className="border border-rose-300 bg-rose-50 text-rose-800 rounded-md p-4 space-y-1">
          {errors.map((e, i) => (
            <p key={i} className="text-sm">
              • {e}
            </p>
          ))}
        </div>
      )}

      {reports && reports.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Wynik weryfikacji</h3>
          {reports.map((r, i) => (
            <div
              key={i}
              className={`rounded-md p-3 text-sm border ${
                r.outcome === "resolved"
                  ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                  : r.outcome === "not_found"
                    ? "border-rose-300 bg-rose-50 text-rose-900"
                    : r.outcome === "error"
                      ? "border-amber-300 bg-amber-50 text-amber-900"
                      : "border-zinc-300 bg-zinc-50 text-zinc-700"
              }`}
            >
              <div className="font-medium">{r.source}</div>
              <div className="text-xs mt-0.5 opacity-80">{r.message}</div>
            </div>
          ))}
        </div>
      )}
    </form>
  );
}
