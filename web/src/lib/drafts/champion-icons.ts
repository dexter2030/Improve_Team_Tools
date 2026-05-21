/**
 * Champion icons z DataDragon.
 *
 * `iconUrl(name)` zwraca URL ikonki championa lub null jeśli nazwa nie
 * pasuje. Wersja DataDragon + mapa nazw → champion id ładuje się raz
 * (lazy, cache w pamięci procesu — singleton).
 *
 * Normalizacja name: alphanum lowercase. Obsługuje "Xin Zhao", "Bel'Veth",
 * "Kha'Zix", "Wukong" itp.
 */

const VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json";

interface DataState {
  version: string;
  map: Map<string, string>; // normalized → champion id
}

let _statePromise: Promise<DataState> | null = null;

async function getState(): Promise<DataState> {
  if (_statePromise) return _statePromise;
  _statePromise = loadState();
  return _statePromise;
}

async function loadState(): Promise<DataState> {
  const versionsRes = await fetch(VERSIONS_URL, {
    next: { revalidate: 86400 },
  });
  const versions = (await versionsRes.json()) as string[];
  const version = versions[0];

  const champUrl = `https://ddragon.leagueoflegends.com/cdn/${version}/data/en_US/champion.json`;
  const champRes = await fetch(champUrl, { next: { revalidate: 86400 } });
  const data = (await champRes.json()) as {
    data: Record<string, { id: string; name: string }>;
  };

  const map = new Map<string, string>();
  for (const champ of Object.values(data.data)) {
    map.set(normalize(champ.name), champ.id);
    map.set(normalize(champ.id), champ.id);
  }
  return { version, map };
}

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export async function iconUrl(champion: string | null | undefined): Promise<string | null> {
  if (!champion) return null;
  try {
    const state = await getState();
    const id = state.map.get(normalize(champion));
    if (!id) return null;
    return `https://ddragon.leagueoflegends.com/cdn/${state.version}/img/champion/${id}.png`;
  } catch {
    return null;
  }
}

/**
 * Wersja synchroniczna — wymaga uprzedniego załadowania state.
 * Zwraca tablicę URLi w jednym round-tripie.
 */
export async function iconUrls(
  champions: (string | null | undefined)[]
): Promise<(string | null)[]> {
  const state = await getState().catch(() => null);
  if (!state) return champions.map(() => null);
  return champions.map((c) => {
    if (!c) return null;
    const id = state.map.get(normalize(c));
    return id
      ? `https://ddragon.leagueoflegends.com/cdn/${state.version}/img/champion/${id}.png`
      : null;
  });
}

/** Lista wszystkich championów (display name) — do autocomplete/select w UI. */
export async function allChampions(): Promise<string[]> {
  try {
    const versionsRes = await fetch(VERSIONS_URL, { next: { revalidate: 86400 } });
    const versions = (await versionsRes.json()) as string[];
    const version = versions[0];
    const champRes = await fetch(
      `https://ddragon.leagueoflegends.com/cdn/${version}/data/en_US/champion.json`,
      { next: { revalidate: 86400 } }
    );
    const data = (await champRes.json()) as {
      data: Record<string, { name: string }>;
    };
    return Object.values(data.data)
      .map((c) => c.name)
      .sort();
  } catch {
    return [];
  }
}
