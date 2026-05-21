"use client";

import { useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { X } from "lucide-react";
import type { DraftPattern } from "@/lib/drafts/analyzer";

interface Props {
  champions: string[];
  initial: DraftPattern;
}

export function SearchGrid({ champions, initial }: Props) {
  const router = useRouter();
  const currentParams = useSearchParams();
  const [pending, startTransition] = useTransition();

  const [bp, setBp] = useState<string[]>(
    initial.bluePicks.map((v) => v ?? "")
  );
  const [rp, setRp] = useState<string[]>(
    initial.redPicks.map((v) => v ?? "")
  );
  const [phase1, setPhase1] = useState<string[]>([...initial.phase1Bans, ""]);
  const [phase2, setPhase2] = useState<string[]>([...initial.phase2Bans, ""]);

  function apply() {
    const params = new URLSearchParams();
    bp.forEach((v, i) => v && params.set(`b${i + 1}`, v));
    rp.forEach((v, i) => v && params.set(`r${i + 1}`, v));
    const p1 = phase1.filter(Boolean);
    const p2 = phase2.filter(Boolean);
    if (p1.length) params.set("phase1Bans", p1.join(","));
    if (p2.length) params.set("phase2Bans", p2.join(","));
    startTransition(() => {
      router.push(`/draft-analyzer/search?${params.toString()}`);
    });
  }

  function clear() {
    setBp(["", "", "", "", ""]);
    setRp(["", "", "", "", ""]);
    setPhase1([""]);
    setPhase2([""]);
    startTransition(() => {
      router.push("/draft-analyzer/search");
    });
  }

  const hasPattern =
    bp.some(Boolean) ||
    rp.some(Boolean) ||
    phase1.some(Boolean) ||
    phase2.some(Boolean);

  return (
    <div className="space-y-6 border rounded-xl p-5 bg-card">
      <datalist id="champion-list">
        {champions.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-blue-700 dark:text-blue-400">
            Blue side picks
          </h3>
          {bp.map((v, i) => (
            <div key={`bp${i}`} className="flex items-center gap-2">
              <Label className="w-8 text-xs text-muted-foreground">B{i + 1}</Label>
              <Input
                list="champion-list"
                placeholder="Champion..."
                value={v}
                onChange={(e) => {
                  const next = [...bp];
                  next[i] = e.target.value;
                  setBp(next);
                }}
              />
            </div>
          ))}
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-rose-700 dark:text-rose-400">
            Red side picks
          </h3>
          {rp.map((v, i) => (
            <div key={`rp${i}`} className="flex items-center gap-2">
              <Label className="w-8 text-xs text-muted-foreground">R{i + 1}</Label>
              <Input
                list="champion-list"
                placeholder="Champion..."
                value={v}
                onChange={(e) => {
                  const next = [...rp];
                  next[i] = e.target.value;
                  setRp(next);
                }}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <BanGroup
          label="Bany fazy 1 (pula obu stron)"
          values={phase1}
          onChange={setPhase1}
        />
        <BanGroup
          label="Bany fazy 2 (pula obu stron)"
          values={phase2}
          onChange={setPhase2}
        />
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={apply} disabled={pending}>
          {pending ? "Szukam..." : "Szukaj draftów"}
        </Button>
        <Button onClick={clear} variant="outline" disabled={pending || !hasPattern}>
          Wyczyść wzorzec
        </Button>
        {currentParams.toString() && (
          <span className="text-xs text-muted-foreground">
            URL można wysłać dalej — wzorzec żyje w query string.
          </span>
        )}
      </div>
    </div>
  );
}

function BanGroup({
  label,
  values,
  onChange,
}: {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  function set(i: number, v: string) {
    const next = [...values];
    next[i] = v;
    // Dodaj pusty input na końcu jeśli wszystkie wypełnione
    if (i === next.length - 1 && v) next.push("");
    onChange(next);
  }
  function remove(i: number) {
    const next = values.filter((_, idx) => idx !== i);
    if (next.length === 0) next.push("");
    onChange(next);
  }
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{label}</h3>
      {values.map((v, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            list="champion-list"
            placeholder="Champion..."
            value={v}
            onChange={(e) => set(i, e.target.value)}
          />
          {v && (
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-muted-foreground hover:text-destructive"
              aria-label="Usuń"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
