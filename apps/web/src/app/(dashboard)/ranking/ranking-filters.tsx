import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";

/**
 * Filtry rankingu (rola + zakres lat) — wspólne dla widoku ligi i narodowości.
 * Zwykły GET-form: pola lądują w query (?role=&from=&to=), stronę renderuje
 * serwer (force-dynamic). `sort` przepuszczamy ukrytym polem, by zmiana filtra
 * nie kasowała aktywnego sortowania.
 */
export function RankingFilters({
  roles,
  years,
  role,
  from,
  to,
  sort,
}: {
  roles: string[];
  years: number[];
  role?: string;
  from?: number;
  to?: number;
  sort: string;
}) {
  const selectClass =
    "border rounded-md px-3 py-2 text-sm bg-background";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Filtry</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3 md:grid-cols-4" method="get">
          <select name="role" defaultValue={role ?? ""} className={selectClass}>
            <option value="">Wszystkie role</option>
            {roles.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <select name="from" defaultValue={from ?? ""} className={selectClass}>
            <option value="">Od roku (najstarszy)</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          <select name="to" defaultValue={to ?? ""} className={selectClass}>
            <option value="">Do roku (najnowszy)</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          {sort !== "rating:desc" && (
            <input type="hidden" name="sort" value={sort} />
          )}
          <button type="submit" className={buttonVariants({ variant: "default" })}>
            Zastosuj
          </button>
        </form>
      </CardContent>
    </Card>
  );
}
