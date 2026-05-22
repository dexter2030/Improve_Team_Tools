import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { ImportForm } from "./import-form";

const EXAMPLE = `displayName\trole\tage\tnationality\topggUrls\tleaguepediaUrl\tnotes
Caps\tMid\t25\tDenmark\thttps://op.gg/lol/summoners/euw/Caps-EUW\thttps://lol.fandom.com/wiki/Caps\tTop EU mid
Faker\tMid\t28\tKorea\thttps://op.gg/lol/summoners/kr/Hide%20on%20bush-KR1\thttps://lol.fandom.com/wiki/Faker\tGOAT`;

export default function ImportPage() {
  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <Link
          href="/scouting"
          className={`${buttonVariants({ variant: "ghost", size: "sm" })} mb-2 -ml-2`}
        >
          <ArrowLeft className="h-4 w-4 mr-1" /> Back to list
        </Link>
        <h2 className="text-2xl font-semibold tracking-tight">
          Bulk import from CSV / TSV
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Paste data from Excel / Google Sheets. One row = one player,
          auto-verified against Riot + Leaguepedia. Per-row errors don&apos;t block the rest.
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4 space-y-2">
        <h3 className="text-sm font-semibold">Required format</h3>
        <p className="text-xs text-muted-foreground">
          Header required. Separator: tab (from Excel) <em>or</em> comma.
          Columns: <code className="text-xs">displayName</code> + <code className="text-xs">role</code> (required),
          plus optional <code className="text-xs">age</code>, <code className="text-xs">nationality</code>,
          <code className="text-xs">opggUrls</code> (multiple separated by &quot;|&quot;),
          <code className="text-xs">leaguepediaUrl</code>,{" "}
          <code className="text-xs">lolprosUrl</code>, <code className="text-xs">notes</code>.
        </p>
        <pre className="text-xs bg-muted p-3 rounded overflow-x-auto whitespace-pre">
{EXAMPLE}
        </pre>
      </div>

      <ImportForm example={EXAMPLE} />
    </div>
  );
}
