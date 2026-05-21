"use client";

import { useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Plus, X, RotateCcw } from "lucide-react";
import { ChampionPicker } from "./champion-picker";
import type { ChampionMeta } from "@/lib/drafts/champion-icons";
import type { SuggestAllResult, SuggestionEntry } from "@/lib/drafts/analyzer";

/**
 * Kolejność draftu w prawdziwych grach (na 2-kolumnowej siatce):
 *   row 1: BB1 | RB1     ← ban phase 1
 *   row 2: BB2 | RB2
 *   row 3: BB3 | RB3
 *   row 4:  B1 |  R1     ← pick phase 1
 *   row 5:  B2 |  R2
 *   row 6:  B3 |  R3
 *   row 7: BB4 | RB4     ← ban phase 2
 *   row 8: BB5 | RB5
 *   row 9:  B4 |  R4     ← pick phase 2
 *   row 10: B5 |  R5
 */

type Side = "blue" | "red";
type Kind = "pick" | "ban";

interface SlotDef {
  label: string;
  side: Side;
  kind: Kind;
  /** Klucz w URL search params. */
  key: string;
  /** Klucz w SuggestAllResult.groups — bp0..bp4 / rp0..rp4 / phase1_bans / phase2_bans. */
  suggestionGroup: string;
}

const ROWS: Array<[SlotDef, SlotDef]> = [
  [
    { label: "BB1", side: "blue", kind: "ban", key: "phase1Bans[0]", suggestionGroup: "phase1_bans" },
    { label: "RB1", side: "red", kind: "ban", key: "phase1Bans[1]", suggestionGroup: "phase1_bans" },
  ],
  [
    { label: "BB2", side: "blue", kind: "ban", key: "phase1Bans[2]", suggestionGroup: "phase1_bans" },
    { label: "RB2", side: "red", kind: "ban", key: "phase1Bans[3]", suggestionGroup: "phase1_bans" },
  ],
  [
    { label: "BB3", side: "blue", kind: "ban", key: "phase1Bans[4]", suggestionGroup: "phase1_bans" },
    { label: "RB3", side: "red", kind: "ban", key: "phase1Bans[5]", suggestionGroup: "phase1_bans" },
  ],
  [
    { label: "B1", side: "blue", kind: "pick", key: "b1", suggestionGroup: "bp0" },
    { label: "R1", side: "red", kind: "pick", key: "r1", suggestionGroup: "rp0" },
  ],
  [
    { label: "B2", side: "blue", kind: "pick", key: "b2", suggestionGroup: "bp1" },
    { label: "R2", side: "red", kind: "pick", key: "r2", suggestionGroup: "rp1" },
  ],
  [
    { label: "B3", side: "blue", kind: "pick", key: "b3", suggestionGroup: "bp2" },
    { label: "R3", side: "red", kind: "pick", key: "r3", suggestionGroup: "rp2" },
  ],
  [
    { label: "BB4", side: "blue", kind: "ban", key: "phase2Bans[0]", suggestionGroup: "phase2_bans" },
    { label: "RB4", side: "red", kind: "ban", key: "phase2Bans[1]", suggestionGroup: "phase2_bans" },
  ],
  [
    { label: "BB5", side: "blue", kind: "ban", key: "phase2Bans[2]", suggestionGroup: "phase2_bans" },
    { label: "RB5", side: "red", kind: "ban", key: "phase2Bans[3]", suggestionGroup: "phase2_bans" },
  ],
  [
    { label: "B4", side: "blue", kind: "pick", key: "b4", suggestionGroup: "bp3" },
    { label: "R4", side: "red", kind: "pick", key: "r4", suggestionGroup: "rp3" },
  ],
  [
    { label: "B5", side: "blue", kind: "pick", key: "b5", suggestionGroup: "bp4" },
    { label: "R5", side: "red", kind: "pick", key: "r5", suggestionGroup: "rp4" },
  ],
];

interface BoardState {
  picks: Record<string, string>;
  phase1Bans: string[];
  phase2Bans: string[];
}

function emptyState(): BoardState {
  return { picks: {}, phase1Bans: ["", "", "", "", "", ""], phase2Bans: ["", "", "", ""] };
}

function fromUrl(sp: URLSearchParams): BoardState {
  const s = emptyState();
  for (const k of ["b1", "b2", "b3", "b4", "b5", "r1", "r2", "r3", "r4", "r5"]) {
    const v = sp.get(k);
    if (v) s.picks[k] = v;
  }
  const p1 = (sp.get("phase1Bans") ?? "").split(",");
  for (let i = 0; i < 6; i++) s.phase1Bans[i] = p1[i] || "";
  const p2 = (sp.get("phase2Bans") ?? "").split(",");
  for (let i = 0; i < 4; i++) s.phase2Bans[i] = p2[i] || "";
  return s;
}

function toUrl(state: BoardState): URLSearchParams {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(state.picks)) {
    if (v) sp.set(k, v);
  }
  const p1 = state.phase1Bans.filter(Boolean);
  if (p1.length > 0) sp.set("phase1Bans", state.phase1Bans.join(","));
  const p2 = state.phase2Bans.filter(Boolean);
  if (p2.length > 0) sp.set("phase2Bans", state.phase2Bans.join(","));
  return sp;
}

export function DraftBoard({
  champions,
  iconByName,
  suggestions,
}: {
  champions: ChampionMeta[];
  iconByName: Record<string, string>;
  /** SuggestAll wynik z serwera — pokazujemy obok pustych slotów. */
  suggestions: SuggestAllResult | null;
}) {
  const router = useRouter();
  const sp = useSearchParams();
  const [, startTransition] = useTransition();
  const [state, setState] = useState<BoardState>(() => fromUrl(sp));
  const [editing, setEditing] = useState<SlotDef | null>(null);

  function valueAt(slot: SlotDef): string {
    if (slot.kind === "pick") return state.picks[slot.key] ?? "";
    const m = slot.key.match(/(phase[12]Bans)\[(\d+)\]/);
    if (!m) return "";
    const [, group, idx] = m;
    const list = group === "phase1Bans" ? state.phase1Bans : state.phase2Bans;
    return list[Number(idx)] ?? "";
  }

  function setSlot(slot: SlotDef, value: string) {
    setState((prev) => {
      const next = {
        ...prev,
        picks: { ...prev.picks },
        phase1Bans: [...prev.phase1Bans],
        phase2Bans: [...prev.phase2Bans],
      };
      if (slot.kind === "pick") {
        if (value) next.picks[slot.key] = value;
        else delete next.picks[slot.key];
      } else {
        const m = slot.key.match(/(phase[12]Bans)\[(\d+)\]/);
        if (m) {
          const list = m[1] === "phase1Bans" ? next.phase1Bans : next.phase2Bans;
          list[Number(m[2])] = value;
        }
      }
      pushUrl(next);
      return next;
    });
  }

  function pushUrl(next: BoardState) {
    const newSp = toUrl(next);
    startTransition(() => {
      router.replace(
        newSp.toString()
          ? `/draft-analyzer/search?${newSp.toString()}`
          : "/draft-analyzer/search"
      );
    });
  }

  function reset() {
    setState(emptyState());
    startTransition(() => router.replace("/draft-analyzer/search"));
  }

  // Wszystkie wybrane (do "used" dla pickera + sugestii — żeby nie pokazywać już użytych).
  const used = [
    ...Object.values(state.picks),
    ...state.phase1Bans,
    ...state.phase2Bans,
  ].filter(Boolean);
  const usedSet = new Set(used);

  const hasAnything = used.length > 0;

  function suggestionsFor(slot: SlotDef): SuggestionEntry[] {
    if (!suggestions) return [];
    const list = suggestions.groups[slot.suggestionGroup] ?? [];
    // Filter out już-użyte i return top 5.
    return list.filter((s) => !usedSet.has(s.champion)).slice(0, 5);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-sm text-muted-foreground">
          Klik slot żeby otworzyć picker, klik sugestię żeby pickować bezpośrednio.
          {suggestions && suggestions.totalMatches > 0 && (
            <span className="ml-2 text-xs">
              Sugestie z <strong>{suggestions.totalMatches}</strong> pasujących pro draftów.
            </span>
          )}
        </div>
        {hasAnything && (
          <Button variant="outline" size="sm" onClick={reset}>
            <RotateCcw className="h-3.5 w-3.5 mr-1" />
            Reset
          </Button>
        )}
      </div>

      <div className="rounded-xl border bg-card overflow-hidden">
        {ROWS.map(([left, right], i) => (
          <div
            key={i}
            className={`grid grid-cols-[1fr_auto_auto_1fr] items-center gap-2 px-2 py-1.5 ${rowBg(
              left.kind
            )} ${i < ROWS.length - 1 ? "border-b" : ""}`}
          >
            {/* Sugestie blue side — po lewej */}
            <SuggestionStrip
              entries={valueAt(left) ? [] : suggestionsFor(left)}
              iconByName={iconByName}
              onPick={(name) => setSlot(left, name)}
              align="right"
            />

            {/* Slot blue */}
            <Slot
              def={left}
              value={valueAt(left)}
              iconByName={iconByName}
              onClear={() => setSlot(left, "")}
              onClick={() => setEditing(left)}
              align="right"
            />

            {/* Slot red */}
            <Slot
              def={right}
              value={valueAt(right)}
              iconByName={iconByName}
              onClear={() => setSlot(right, "")}
              onClick={() => setEditing(right)}
              align="left"
            />

            {/* Sugestie red side — po prawej */}
            <SuggestionStrip
              entries={valueAt(right) ? [] : suggestionsFor(right)}
              iconByName={iconByName}
              onPick={(name) => setSlot(right, name)}
              align="left"
            />
          </div>
        ))}
      </div>

      {editing && (
        <ChampionPicker
          champions={champions}
          open={true}
          onOpenChange={(o) => !o && setEditing(null)}
          slotLabel={editing.label}
          side={editing.side}
          kind={editing.kind}
          used={used}
          onPick={(name) => {
            setSlot(editing, name);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function rowBg(kind: Kind): string {
  return kind === "ban"
    ? "bg-rose-950/20 dark:bg-rose-950/30"
    : "bg-emerald-950/20 dark:bg-emerald-950/30";
}

/** Pasek 5 mini-ikonek sugestii. Pusty array = nic nie renderuje. */
function SuggestionStrip({
  entries,
  iconByName,
  onPick,
  align,
}: {
  entries: SuggestionEntry[];
  iconByName: Record<string, string>;
  onPick: (name: string) => void;
  align: "left" | "right";
}) {
  return (
    <div
      className={`flex items-center gap-1 ${
        align === "right" ? "justify-end" : "justify-start"
      }`}
    >
      {entries.map((e) => {
        const icon = iconByName[e.champion];
        return (
          <button
            key={e.champion}
            onClick={() => onPick(e.champion)}
            title={`${e.champion} — ${e.count}× (${e.pct.toFixed(0)}%)`}
            className="relative h-8 w-8 rounded border-2 border-transparent hover:border-primary hover:scale-110 transition-all overflow-hidden"
          >
            {icon ? (
              <img
                src={icon}
                alt={e.champion}
                loading="lazy"
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-[8px]">{e.champion.slice(0, 3)}</span>
            )}
            <span className="absolute bottom-0 right-0 bg-black/60 text-white text-[8px] px-0.5 rounded-tl">
              {e.pct.toFixed(0)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function Slot({
  def,
  value,
  iconByName,
  onClick,
  onClear,
  align,
}: {
  def: SlotDef;
  value: string;
  iconByName: Record<string, string>;
  onClick: () => void;
  onClear: () => void;
  align: "left" | "right";
}) {
  const sideColor =
    def.side === "blue"
      ? "border-blue-500/60 text-blue-700 dark:text-blue-400"
      : "border-rose-500/60 text-rose-700 dark:text-rose-400";
  const icon = value ? iconByName[value] : null;

  return (
    <div
      className={`flex items-center gap-1.5 ${
        align === "right" ? "flex-row-reverse" : ""
      }`}
    >
      <button
        onClick={onClick}
        className={`flex items-center justify-center w-10 h-8 rounded border text-[10px] font-mono font-bold transition-colors ${sideColor} hover:bg-muted/50 shrink-0`}
      >
        {def.label}
      </button>

      <button
        onClick={onClick}
        className={`flex items-center justify-center h-8 w-10 rounded border border-dashed transition-colors shrink-0 ${
          value
            ? "border-foreground/20 bg-background/60"
            : "border-foreground/15 hover:border-foreground/40 hover:bg-muted/40"
        }`}
        title={value || "Kliknij żeby wybrać championa"}
      >
        {value && icon ? (
          <img
            src={icon}
            alt={value}
            className="h-7 w-7 rounded"
            loading="lazy"
          />
        ) : (
          <Plus className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>

      {value && (
        <button
          onClick={onClear}
          className="text-muted-foreground hover:text-destructive p-0.5"
          title="Wyczyść slot"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
