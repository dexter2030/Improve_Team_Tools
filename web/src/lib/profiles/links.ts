/**
 * Parsery URL → identity keys.
 *
 * Port src/processing/links.py — zamienia linki, które coach wkleja, na
 * klucze których faktycznie potrzebują API clienty.
 *
 *   op.gg URL        → (riotId, platform)   — dla RiotClient.resolveAccount
 *   Leaguepedia URL  → page name (`Link`)   — dla LeaguepediaClient.getPlayers
 */

import { PlatformRouting } from "@/lib/riot/types";

/** op.gg ma własne kody regionów; mapujemy na Riot platform routing. */
const OPGG_REGION_TO_PLATFORM: Record<string, PlatformRouting> = {
  na: "na1",
  euw: "euw1",
  eune: "eun1",
  kr: "kr",
  jp: "jp1",
  oce: "oc1",
  lan: "la1",
  las: "la2",
  br: "br1",
  tr: "tr1",
  ru: "ru",
};

export interface OpggResult {
  riotId: string; // "GameName#TAG"
  platform: PlatformRouting;
}

export function parseOpggUrl(url: string): OpggResult {
  const raw = url.trim();
  if (!raw) throw new Error("Empty op.gg URL.");

  const parsed = safeParse(raw);
  if (!parsed.hostname.toLowerCase().includes("op.gg")) {
    throw new Error(`Not an op.gg URL: '${url}'.`);
  }

  const parts = parsed.pathname.split("/").filter(Boolean);
  const i = parts.indexOf("summoners");
  if (i < 0) {
    throw new Error(
      `Unrecognized op.gg URL '${url}'. Expected a summoner link like ` +
        `https://op.gg/lol/summoners/<region>/<GameName>-<TAG>.`
    );
  }

  const region = parts[i + 1]?.toLowerCase();
  const nameTagRaw = parts[i + 2];
  if (!region || !nameTagRaw) {
    throw new Error(`op.gg URL '${url}' is missing the region or summoner name.`);
  }

  const platform = OPGG_REGION_TO_PLATFORM[region];
  if (!platform) {
    const known = Object.keys(OPGG_REGION_TO_PLATFORM).sort().join(", ");
    throw new Error(
      `Unsupported op.gg region '${region}' in '${url}'. Supported: ${known}.`
    );
  }

  // op.gg łączy GameName z tag line OSTATNIM hyphenem (game name może mieć
  // hyphen, tag line nigdy).
  const nameTag = decodeURIComponent(nameTagRaw);
  const idx = nameTag.lastIndexOf("-");
  if (idx <= 0 || idx === nameTag.length - 1) {
    throw new Error(
      `Could not read a 'GameName-TAG' from op.gg URL '${url}'. ` +
        `Make sure it is a current op.gg summoner link.`
    );
  }
  const gameName = nameTag.slice(0, idx).trim();
  const tagLine = nameTag.slice(idx + 1).trim();
  if (!gameName || !tagLine) {
    throw new Error(`op.gg URL '${url}' has empty GameName or TAG.`);
  }

  return { riotId: `${gameName}#${tagLine}`, platform };
}

export function parseLeaguepediaUrl(url: string): string {
  const raw = url.trim();
  if (!raw) throw new Error("Empty Leaguepedia URL.");

  const parsed = safeParse(raw);
  const host = parsed.hostname.toLowerCase();
  if (!host.includes("fandom.com") && !host.includes("leaguepedia")) {
    throw new Error(`Not a Leaguepedia URL: '${url}'.`);
  }

  const idx = parsed.pathname.indexOf("/wiki/");
  if (idx < 0) {
    throw new Error(
      `Leaguepedia URL '${url}' must point at a wiki page (.../wiki/<PageName>).`
    );
  }
  const page = decodeURIComponent(parsed.pathname.slice(idx + "/wiki/".length))
    .trim()
    .replace(/_/g, " ");
  if (!page) {
    throw new Error(`Leaguepedia URL '${url}' has empty page name.`);
  }
  return page;
}

// --- Helpers ----------------------------------------------------------------

function safeParse(raw: string): URL {
  try {
    return new URL(raw.includes("//") ? raw : `https://${raw}`);
  } catch {
    throw new Error(`Invalid URL: '${raw}'.`);
  }
}
