import { describe, it, expect } from "vitest";
import { isSchemaBehindError } from "./schema-error";

describe("isSchemaBehindError", () => {
  it("undefined_table (42P01) => true", () => {
    expect(isSchemaBehindError({ code: "42P01" })).toBe(true);
  });

  it("undefined_column (42703) => true", () => {
    expect(isSchemaBehindError({ code: "42703" })).toBe(true);
  });

  it("inny błąd Postgresa (np. unique_violation 23505) => false", () => {
    expect(isSchemaBehindError({ code: "23505" })).toBe(false);
  });

  it("zwykły Error bez kodu => false (poleci do error boundary)", () => {
    expect(isSchemaBehindError(new Error("connection refused"))).toBe(false);
  });

  it("null/undefined => false", () => {
    expect(isSchemaBehindError(null)).toBe(false);
    expect(isSchemaBehindError(undefined)).toBe(false);
  });

  it("kod nie-string => false", () => {
    expect(isSchemaBehindError({ code: 42703 })).toBe(false);
  });
});
