"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, X } from "lucide-react";
import type { ChampionMeta } from "@/lib/drafts/champion-icons";

const TAGS = ["All", "Fighter", "Tank", "Mage", "Assassin", "Marksman", "Support"] as const;
type Tag = (typeof TAGS)[number];

interface Props {
  champions: ChampionMeta[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slotLabel: string;
  side: "blue" | "red";
  kind: "pick" | "ban";
  /** Lista championów już użytych w drafcie — wyszarzone w pickerze. */
  used: string[];
  onPick: (championName: string) => void;
}

export function ChampionPicker({
  champions,
  open,
  onOpenChange,
  slotLabel,
  side,
  kind,
  used,
  onPick,
}: Props) {
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<Tag>("All");

  // Reset state when closing.
  useEffect(() => {
    if (!open) {
      setQuery("");
      setTag("All");
    }
  }, [open]);

  const usedSet = useMemo(() => new Set(used), [used]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return champions.filter((c) => {
      if (tag !== "All" && !c.tags.includes(tag)) return false;
      if (q && !c.name.toLowerCase().includes(q) && !c.id.toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [champions, query, tag]);

  // Enter pick'uje pierwszy match (jak w drafttool).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!open) return;
      if (e.key === "Enter" && filtered.length > 0) {
        e.preventDefault();
        onPick(filtered[0].name);
        onOpenChange(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, onPick, onOpenChange]);

  const accent =
    side === "blue"
      ? "border-blue-500/40"
      : "border-rose-500/40";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl p-0 overflow-hidden">
        <DialogHeader className="p-4 pb-2">
          <DialogTitle className="text-sm">
            <span className="text-muted-foreground">{kind === "ban" ? "Ban" : "Pick"} for slot</span>{" "}
            <span className={`inline-block px-2 py-0.5 rounded font-mono text-xs border ${accent}`}>
              {slotLabel}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="px-4 pb-3 space-y-3">
          <div className="relative">
            <Search className="h-4 w-4 absolute left-2.5 top-2.5 text-muted-foreground" />
            <Input
              autoFocus
              placeholder="Search champions..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-8"
            />
          </div>

          <div className="flex flex-wrap gap-1">
            {TAGS.map((t) => (
              <button
                key={t}
                onClick={() => setTag(t)}
                className={`text-xs px-2 py-1 rounded border transition-colors ${
                  tag === t
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border hover:bg-muted"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="px-4 pb-4 max-h-[400px] overflow-y-auto">
          <div className="grid grid-cols-7 sm:grid-cols-8 gap-1.5">
            {filtered.map((c) => {
              const isUsed = usedSet.has(c.name);
              return (
                <button
                  key={c.id}
                  disabled={isUsed}
                  onClick={() => {
                    onPick(c.name);
                    onOpenChange(false);
                  }}
                  title={c.name + (isUsed ? " (already in draft)" : "")}
                  className={`relative aspect-square rounded overflow-hidden border-2 transition-all ${
                    isUsed
                      ? "border-transparent opacity-30 cursor-not-allowed"
                      : "border-transparent hover:border-primary hover:scale-105 cursor-pointer"
                  }`}
                >
                  <img
                    src={c.iconUrl}
                    alt={c.name}
                    loading="lazy"
                    className="w-full h-full object-cover"
                  />
                </button>
              );
            })}
          </div>
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">
              No champions matching &quot;{query}&quot;.
            </p>
          )}
        </div>

        <div className="px-4 py-3 border-t bg-muted/30 flex items-center justify-between text-xs">
          <span className="text-muted-foreground">
            {filtered.length} champions{filtered[0] ? ` · ENTER = ${filtered[0].name}` : ""}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            <X className="h-3 w-3 mr-1" />
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
