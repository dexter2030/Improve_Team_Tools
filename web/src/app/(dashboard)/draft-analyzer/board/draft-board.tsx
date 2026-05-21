"use client";

import { useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Plus, X, RotateCcw, Search } from "lucide-react";
import { ChampionPicker } from "./champion-picker";
import type { ChampionMeta } from "@/lib/drafts/champion-icons";

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
}

const ROWS: Array<[SlotDef, SlotDef]> = [
  [
    { label: "BB1", side: "blue", kind: "ban", key: "phase1Bans[0]" },
    { label: "RB1", side: "red", kind: "ban", key: "phase1Bans[1]" },
  ],
  [
    { label: "BB2", side: "blue", kind: "ban", key: "phase1Bans[2]" },
    { label: "RB2", side: "red", kind: "ban", key: "phase1Bans[3]" },
  ],
  [
    { label: "BB3", side: "blue", kind: "ban", key: "phase1Bans[4]" },
    { label: "RB3", side: "red", kind: "ban", key: "phase1Bans[5]" },
  ],
  [
    { label: "B1", side: "blue", kind: "pick", key: "b1" },
    { label: "R1", side: "red", kind: "pick", key: "r1" },
  ],
  [
    { label: "B2", side: "blue", kind: "pick", key: "b2" },
    { label: "R2", side: "red", kind: "pick", key: "r2" },
  ],
  [
    { label: "B3", side: "blue", kind: "pick", key: "b3" },
    { label: "R3", side: "red", kind: "pick", key: "r3" },
  ],
  [
    { label: "BB4", side: "blue", kind: "ban", key: "phase2Bans[0]" },
    { label: "RB4", side: "red", kind: "ban", key: "phase2Bans[1]" },
  ],
  [
    { label: "BB5", side: "blue", kind: "ban", key: "phase2Bans[2]" },
    { label: "RB5", side: "red", kind: "ban", key: "phase2Bans[3]" },
  ],
  [
    { label: "B4", side: "blue", kind: "pick", key: "b4" },
    { label: "R4", side: "red", kind: "pick", key: "r4" },
  ],
  [
    { label: "B5", side: "blue", kind: "pick", key: "b5" },
    { label: "R5", side: "red", kind: "pick", key: "r5" },
  ],
];

interface BoardState {
  // Picks: B1..B5, R1..R5 — pojedyncze stringi.
  picks: Record<string, string>; // key="b1" → name
  // Bans: phase1 (6 sloty, blue+red interleaved B1B,R1B,B2B,R2B,B3B,R3B),
  // phase2 (4 sloty B4B,R4B,B5B,R5B). Indeksy 0..5 / 0..3.
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
  initialMatches,
}: {
  champions: ChampionMeta[];
  iconByName: Record<string, string>;
  initialMatches: number;
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
          ? `/draft-analyzer/board?${newSp.toString()}`
          : "/draft-analyzer/board"
      );
    });
  }

  function reset() {
    setState(emptyState());
    startTransition(() => router.replace("/draft-analyzer/board"));
  }

  // Wszystkie wybrane (do "used" dla pickera — same champion nie powinien być dwa razy).
  const used = [
    ...Object.values(state.picks),
    ...state.phase1Bans,
    ...state.phase2Bans,
  ].filter(Boolean);

  const hasAnything = used.length > 0;
  const searchUrl = `/draft-analyzer/search?${toUrl(state).toString()}`;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">
            Klikaj sloty żeby ustawić championy. Stan w URL — można udostępniać.
          </span>
        </div>
        <div className="flex items-center gap-2">
          {hasAnything && (
            <>
              <Button variant="outline" size="sm" onClick={reset}>
                <RotateCcw className="h-3.5 w-3.5 mr-1" />
                Reset
              </Button>
              <Link
                href={searchUrl}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-md bg-primary text-primary-foreground hover:opacity-90"
              >
                <Search className="h-3.5 w-3.5" />
                Pokaż pasujące drafty
                {initialMatches > 0 && (
                  <span className="ml-1 px-1.5 py-0.5 text-[10px] bg-primary-foreground/20 rounded">
                    {initialMatches}
                  </span>
                )}
              </Link>
            </>
          )}
        </div>
      </div>

      <div className="rounded-xl border bg-card overflow-hidden">
        {ROWS.map(([left, right], i) => (
          <div
            key={i}
            className={`grid grid-cols-2 ${rowBg(left.kind)} ${
              i < ROWS.length - 1 ? "border-b" : ""
            }`}
          >
            <Slot
              def={left}
              value={valueAt(left)}
              iconByName={iconByName}
              onClear={() => setSlot(left, "")}
              onClick={() => setEditing(left)}
              align="right"
            />
            <Slot
              def={right}
              value={valueAt(right)}
              iconByName={iconByName}
              onClear={() => setSlot(right, "")}
              onClick={() => setEditing(right)}
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
      ? "border-blue-500/40 text-blue-700 dark:text-blue-400"
      : "border-rose-500/40 text-rose-700 dark:text-rose-400";
  const icon = value ? iconByName[value] : null;

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 ${
        align === "right" ? "flex-row-reverse" : ""
      }`}
    >
      <button
        onClick={onClick}
        className={`flex items-center gap-2 px-2 py-1 rounded border text-xs font-mono font-semibold transition-colors ${sideColor} ${
          align === "right" ? "flex-row-reverse" : ""
        } hover:bg-muted/50`}
      >
        <span>{def.label}</span>
      </button>

      <button
        onClick={onClick}
        className={`flex-1 max-w-[260px] flex items-center gap-2 px-2 py-1.5 rounded border border-dashed transition-colors ${
          align === "right" ? "flex-row-reverse" : ""
        } ${
          value
            ? "border-foreground/20 bg-background/60"
            : "border-foreground/10 hover:border-foreground/30 hover:bg-muted/40"
        }`}
      >
        {value ? (
          <>
            {icon && (
              <img
                src={icon}
                alt={value}
                className="h-7 w-7 rounded"
                loading="lazy"
              />
            )}
            <span className="text-xs truncate flex-1 text-left">{value}</span>
          </>
        ) : (
          <>
            <Plus className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground italic">puste</span>
          </>
        )}
      </button>

      {value && (
        <button
          onClick={onClear}
          className="text-muted-foreground hover:text-destructive p-1"
          title="Wyczyść slot"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
