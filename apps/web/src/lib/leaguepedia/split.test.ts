import { describe, it, expect } from "vitest";
import { deriveSplit, splitFraction, SPLIT_FALLBACK } from "./split";

describe("deriveSplit", () => {
  it("priorytet Tournaments.Split", () => {
    expect(deriveSplit("Spring", "LEC/2025 Season/Summer Season", "LEC 2025 Summer")).toBe("Spring");
  });

  it("fallback do nazwy strony, gdy Split pusty", () => {
    expect(deriveSplit("", "LEC/2025 Season/Winter Season", "")).toBe("Winter");
  });

  it("fallback do nazwy turnieju, gdy strona nic nie daje", () => {
    expect(deriveSplit("", "", "LFL 2024 Summer")).toBe("Summer");
  });

  it("rozpoznaje 'Split N'", () => {
    expect(deriveSplit("Split 2", "", "")).toBe("Split 2");
  });

  it("event bez splitu => SPLIT_FALLBACK", () => {
    expect(deriveSplit("", "MSI 2025", "Mid-Season Invitational 2025")).toBe(SPLIT_FALLBACK);
  });
});

describe("splitFraction", () => {
  it("SplitNumber ma priorytet i rośnie", () => {
    expect(splitFraction(1, "Summer", 7)).toBeLessThan(splitFraction(2, "Summer", 1));
  });

  it("z etykiety: Winter < Spring < Summer", () => {
    const w = splitFraction(null, "Winter", 1);
    const sp = splitFraction(null, "Spring", 1);
    const su = splitFraction(null, "Summer", 1);
    expect(w).toBeLessThan(sp);
    expect(sp).toBeLessThan(su);
  });

  it("fallback po miesiącu, gdy brak SplitNumber i nieznana etykieta", () => {
    expect(splitFraction(null, SPLIT_FALLBACK, 1)).toBeLessThan(
      splitFraction(null, SPLIT_FALLBACK, 12)
    );
  });

  it("ułamek zawsze w [0,1)", () => {
    for (const f of [
      splitFraction(9, "x", 6),
      splitFraction(null, "Summer", 12),
      splitFraction(null, "x", 12),
    ]) {
      expect(f).toBeGreaterThanOrEqual(0);
      expect(f).toBeLessThan(1);
    }
  });
});
