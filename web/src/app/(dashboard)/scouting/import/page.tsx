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
          <ArrowLeft className="h-4 w-4 mr-1" /> Z powrotem do listy
        </Link>
        <h2 className="text-2xl font-semibold tracking-tight">
          Bulk import z CSV / TSV
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Wklej dane z Excela / Google Sheets. Każdy wiersz =
          jeden gracz, automatycznie zweryfikowany przez Riot + Leaguepedia.
          Błędy per-wiersz nie blokują pozostałych.
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4 space-y-2">
        <h3 className="text-sm font-semibold">Wymagany format</h3>
        <p className="text-xs text-muted-foreground">
          Header obowiązkowy. Separator: tab (z Excela) <em>lub</em> przecinek.
          Kolumny: <code className="text-xs">displayName</code> + <code className="text-xs">role</code> (wymagane),
          oraz opcjonalnie <code className="text-xs">age</code>, <code className="text-xs">nationality</code>,
          <code className="text-xs">opggUrls</code> (wiele rozdzielonych "|"),
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
