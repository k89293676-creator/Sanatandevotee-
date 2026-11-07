import { describe, it, expect } from "vitest";
import { setClock, now, realClock, resetClock } from "../src/clock";

describe("clock", () => {
  it("injects fake time", () => {
    const fake = { now: () => new Date("2025-01-01T00:00:00Z") };
    setClock(fake);
    expect(now().toISOString()).toBe("2025-01-01T00:00:00.000Z");
    resetClock();
  });
});