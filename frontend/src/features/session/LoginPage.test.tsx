import { describe, expect, it } from "vitest";
import { safeNext } from "./LoginPage";

describe("safeNext", () => {
  it.each([
    null,
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/\\\\evil.example",
    "//[invalid",
  ])("rejects unsafe redirect %s", (value) =>
    expect(safeNext(value)).toBe("/"),
  );

  it("preserves local paths, queries and fragments", () => {
    expect(safeNext("/chat/42?view=story#turn-3")).toBe(
      "/chat/42?view=story#turn-3",
    );
  });
});
