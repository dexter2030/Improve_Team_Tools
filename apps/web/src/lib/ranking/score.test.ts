import { describe, it, expect } from "vitest";
import type { LpPlayerStat } from "@/lib/db/schema";
import { buildCohorts } from "./cohort";
import {
  ageFactor,
  composeYearZ,
  rankLeague,
  tierForZ,
  to100,
  weightedSlope,
  type PlayerCareer,
} from "./score";

// --- Helpery ----------------------------------------------------------------

function stat(
  o: Partial<LpPlayerStat> & {
    overviewPage: string;
    year: number;
    league: string;
    role: string;
    games: number;
  }
): LpPlayerStat {
  return {
    wins: 0,
    winrate: 0.5,
    kda: null,
    csPerMin: null,
    dpm: null,
    kp: null,
    goldShare: null,
    syncedAt: new Date(0),
    ...o,
  } as LpPlayerStat;
}

/** Kohorta n „przeciętnych" midów w danej lidze/roku (rozrzut → std > 0). */
function baseline(league: string, year: number, n = 5): LpPlayerStat[] {
  const rows: LpPlayerStat[] = [];
  for (let i = 0; i < n; i++) {
    const d = i - (n - 1) / 2; // wyśrodkowany rozrzut
    rows.push(
      stat({
        overviewPage: `Base_${league}_${year}_${i}`,
        year,
        league,
        role: "Mid",
        games: 20,
        kda: 3.0 + d * 0.3,
        csPerMin: 8.0 + d * 0.2,
        dpm: 450 + d * 20,
        kp: 0.65 + d * 0.02,
        goldShare: 0.22 + d * 0.005,
      })
    );
  }
  return rows;
}

function groupPlayers(
  all: LpPlayerStat[],
  birthdates: Record<string, Date | null>
): PlayerCareer[] {
  const byPlayer = new Map<string, LpPlayerStat[]>();
  for (const s of all) {
    const arr = byPlayer.get(s.overviewPage) ?? [];
    arr.push(s);
    byPlayer.set(s.overviewPage, arr);
  }
  return [...byPlayer.entries()].map(([overviewPage, seasons]) => ({
    overviewPage,
    seasons,
    birthdate: birthdates[overviewPage] ?? null,
  }));
}

// --- Helpery skali ----------------------------------------------------------

describe("ageFactor", () => {
  it("młodszy => wyższy sufit, ~22 neutralne", () => {
    expect(ageFactor(17)).toBeGreaterThan(ageFactor(22));
    expect(ageFactor(22)).toBeGreaterThan(ageFactor(28));
    expect(ageFactor(22)).toBeCloseTo(0, 5);
  });
  it("brzegi krzywej są płaskie", () => {
    expect(ageFactor(10)).toBe(1.0);
    expect(ageFactor(40)).toBe(-0.9);
  });
});

describe("weightedSlope", () => {
  it("rosnąca seria => nachylenie +1/rok", () => {
    expect(
      weightedSlope([
        { x: 2023, y: 0, w: 1 },
        { x: 2024, y: 1, w: 1 },
        { x: 2025, y: 2, w: 1 },
      ])
    ).toBeCloseTo(1, 6);
  });
  it("mniej niż 2 punkty => 0", () => {
    expect(weightedSlope([{ x: 2025, y: 5, w: 1 }])).toBe(0);
  });
});

describe("to100 / tierForZ", () => {
  it("z=0 => 50 pkt", () => {
    expect(to100(0)).toBeCloseTo(50, 6);
  });
  it("wyższy Z => wyższy tier", () => {
    expect(tierForZ(2)).toBe("S");
    expect(tierForZ(0)).toBe("B");
    expect(tierForZ(-2)).toBe("D");
  });
});

// --- Kohorta / Z-score ------------------------------------------------------

describe("buildCohorts + composeYearZ", () => {
  it("wartości powyżej średniej kohorty => dodatni composite Z", () => {
    const cohorts = buildCohorts(baseline("LFL", 2025));
    const high = {
      year: 2025,
      league: "LFL",
      role: "Mid",
      games: 20,
      kda: 5,
      csPerMin: 9,
      dpm: 600,
      kp: 0.8,
      goldShare: 0.3,
    };
    const z = composeYearZ(high, cohorts);
    expect(z).not.toBeNull();
    expect(z as number).toBeGreaterThan(0);
  });

  it("brak kohorty => null (sezon pomijany w scoringu)", () => {
    const cohorts = buildCohorts(baseline("LFL", 2025));
    const orphan = {
      year: 2019,
      league: "LCK",
      role: "Mid",
      games: 20,
      kda: 5,
      csPerMin: 9,
      dpm: 600,
      kp: 0.8,
      goldShare: 0.3,
    };
    expect(composeYearZ(orphan, cohorts)).toBeNull();
  });
});

// --- rankLeague end-to-end --------------------------------------------------

describe("rankLeague", () => {
  // Młody, rosnący gracz wspinający się ERL D2 -> ERL D1 vs starszy, stabilny weteran.
  const rising: LpPlayerStat[] = [
    stat({ overviewPage: "Rising", year: 2023, league: "LFL Division 2", role: "Mid", games: 18, kda: 3.5, csPerMin: 8.2, dpm: 470, kp: 0.66, goldShare: 0.23 }),
    stat({ overviewPage: "Rising", year: 2024, league: "LFL", role: "Mid", games: 22, kda: 3.6, csPerMin: 8.4, dpm: 485, kp: 0.68, goldShare: 0.235 }),
    stat({ overviewPage: "Rising", year: 2025, league: "LFL", role: "Mid", games: 24, kda: 4.9, csPerMin: 9.1, dpm: 545, kp: 0.73, goldShare: 0.25 }),
  ];
  const veteran: LpPlayerStat[] = [
    stat({ overviewPage: "Veteran", year: 2024, league: "LFL", role: "Mid", games: 24, kda: 4.6, csPerMin: 8.9, dpm: 535, kp: 0.71, goldShare: 0.248 }),
    stat({ overviewPage: "Veteran", year: 2025, league: "LFL", role: "Mid", games: 24, kda: 4.6, csPerMin: 8.9, dpm: 535, kp: 0.71, goldShare: 0.248 }),
  ];

  const all = [
    ...baseline("LFL", 2025),
    ...baseline("LFL", 2024),
    ...rising,
    ...veteran,
  ];
  const cohorts = buildCohorts(all);
  const players = groupPlayers(all, {
    Rising: new Date("2007-01-01T00:00:00Z"), // 18 lat w 2025
    Veteran: new Date("1997-01-01T00:00:00Z"), // 28 lat w 2025
  });
  const ranked = rankLeague({ league: "LFL", players, cohorts });
  const byId = Object.fromEntries(ranked.map((p) => [p.overviewPage, p]));

  it("obaj wyróżniający się gracze są ocenieni wysoko", () => {
    expect(byId.Rising.rating).toBeGreaterThan(60);
    expect(byId.Veteran.rating).toBeGreaterThan(60);
  });

  it("młody rosnący ma wyższy POTENCJAŁ niż stary stabilny weteran", () => {
    expect(byId.Rising.potential).toBeGreaterThan(byId.Veteran.potential);
  });

  it("perYear pokrywa całą karierę (też ligę spoza rankowanej)", () => {
    expect(byId.Rising.perYear.length).toBe(3);
    expect(byId.Rising.perYear.map((y) => y.year)).toEqual([2023, 2024, 2025]);
  });

  it("wynik posortowany malejąco po ocenie", () => {
    for (let i = 1; i < ranked.length; i++) {
      expect(ranked[i - 1].rating).toBeGreaterThanOrEqual(ranked[i].rating);
    }
  });

  it("filtr roli odrzuca inne role", () => {
    const onlySupport = rankLeague({
      league: "LFL",
      players,
      cohorts,
      roleFilter: "Support",
    });
    expect(onlySupport.length).toBe(0);
  });
});
