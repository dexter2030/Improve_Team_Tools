/**
 * Champion ikona + nazwa w jednej komórce tabeli / liście.
 * Server Component — iconUrl() jest awaitable, robimy raz per render.
 */

import { iconUrl } from "@/lib/drafts/champion-icons";

export async function ChampionCell({
  name,
  size = 28,
}: {
  name: string | null | undefined;
  size?: number;
}) {
  if (!name) return <span className="text-muted-foreground">—</span>;
  const url = await iconUrl(name);
  return (
    <div className="flex items-center gap-1.5">
      {url && (
        <img
          src={url}
          alt={name}
          width={size}
          height={size}
          className="rounded"
        />
      )}
      <span className="text-xs">{name}</span>
    </div>
  );
}

export async function ChampionIcon({
  name,
  size = 24,
}: {
  name: string | null | undefined;
  size?: number;
}) {
  if (!name) return null;
  const url = await iconUrl(name);
  if (!url) return <span className="text-xs">{name}</span>;
  return (
    <img
      src={url}
      alt={name}
      width={size}
      height={size}
      className="rounded"
      title={name}
    />
  );
}
