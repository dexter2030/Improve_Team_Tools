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
import { addProfileAction } from "../actions";
import type { SourceReport } from "@/lib/profiles";

const ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"] as const;

export function AddPlayerForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [reports, setReports] = useState<SourceReport[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [role, setRole] = useState<string>("Mid");

  function onSubmit(formData: FormData) {
    setReports(null);
    setErrors([]);
    formData.set("role", role); // Select nie pushuje value do FormData automatycznie
    startTransition(async () => {
      const result = await addProfileAction(formData);
      if (!result.ok) {
        setErrors(result.errors ?? ["Nieznany błąd."]);
        toast.error("Nie udało się dodać profilu.");
        return;
      }
      setReports(result.reports ?? []);
      toast.success("Profil dodany — kliknij żeby zobaczyć szczegóły.", {
        action: result.profileId
          ? {
              label: "Otwórz",
              onClick: () => router.push(`/scouting/${result.profileId}`),
            }
          : undefined,
      });
      // Po sukcesie wracamy do listy, ale po krótkiej chwili żeby user
      // zobaczył raporty per-source.
      setTimeout(() => router.push("/scouting"), 2500);
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
            placeholder="Jak go nazywasz"
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="role">Rola *</Label>
          <Select value={role} onValueChange={(v) => setRole(v ?? "Mid")}>
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
            placeholder="18"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="nationality">Kraj</Label>
          <Input id="nationality" name="nationality" placeholder="np. Polska" />
        </div>

        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="leaguepediaUrl">Link Leaguepedia</Label>
          <Input
            id="leaguepediaUrl"
            name="leaguepediaUrl"
            placeholder="https://lol.fandom.com/wiki/..."
          />
        </div>

        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="lolprosUrl">Link lolpros</Label>
          <Input
            id="lolprosUrl"
            name="lolprosUrl"
            placeholder="https://lolpros.gg/player/..."
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="opggUrls">Linki op.gg — jeden na linię</Label>
        <Textarea
          id="opggUrls"
          name="opggUrls"
          rows={4}
          placeholder={
            "https://op.gg/lol/summoners/euw/Nazwa-TAG\nhttps://op.gg/lol/summoners/kr/Inne-TAG"
          }
        />
        <p className="text-xs text-muted-foreground">
          Każdy link op.gg to osobne konto SoloQ — dodaj ich dowolnie wiele.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="notes">Notatka</Label>
        <Textarea
          id="notes"
          name="notes"
          rows={5}
          placeholder="Twoja ocena gracza..."
        />
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? "Weryfikuję..." : "Dodaj i zweryfikuj"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => router.push("/scouting")}
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
