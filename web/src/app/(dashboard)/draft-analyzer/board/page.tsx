import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { allChampionsMeta } from "@/lib/drafts/champion-icons";
import { getAllDrafts } from "@/lib/drafts/repository";
import {
  searchDrafts,
  isPatternEmpty,
  type DraftPattern,
} from "@/lib/drafts/analyzer";
import { DraftBoard } from "./draft-board";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<Record<string, string | undefined>>;
}

export default async function DraftBoardPage({ searchParams }: Props) {
  const sp = await searchParams;
  const pattern = parsePattern(sp);

  const champions = await allChampionsMeta();
  const iconByName: Record<string, string> = {};
  for (const c of champions) iconByName[c.name] = c.iconUrl;

  let matchCount = 0;
  if (!isPatternEmpty(pattern)) {
    try {
      const all = await getAllDrafts();
      matchCount = searchDrafts(all, pattern).length;
    } catch {
      // brak DB — pokażemy 0 matches, board sam działa client-side
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/draft-analyzer"
          className={`${buttonVariants({ variant: "ghost", size: "sm" })} mb-2 -ml-2`}
        >
          <ArrowLeft className="h-4 w-4 mr-1" /> Powrót do analyzera
        </Link>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">
              Draft Board
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Interaktywna siatka pick &amp; ban. Klikaj sloty żeby ustawić
              championy — pasujące pro drafty znajdziesz pod przyciskiem
              "Pokaż pasujące drafty".
            </p>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Pick &amp; ban</CardTitle>
          <CardDescription>
            Kolejność wierszy odpowiada kolejności wyborów w prawdziwym pro
            drafcie (BB1-3 → RB1-3 → B1 → R1-2 → B2-3 → R3 → BB4-5 → RB4-5 →
            B4-5 → R4-5).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DraftBoard
            champions={champions}
            iconByName={iconByName}
            initialMatches={matchCount}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function parsePattern(sp: Record<string, string | undefined>): DraftPattern {
  const get = (k: string): string | null => (sp[k] || "").trim() || null;
  const list = (k: string): string[] =>
    (sp[k] || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  return {
    bluePicks: ["b1", "b2", "b3", "b4", "b5"].map(get),
    redPicks: ["r1", "r2", "r3", "r4", "r5"].map(get),
    phase1Bans: list("phase1Bans"),
    phase2Bans: list("phase2Bans"),
  };
}
