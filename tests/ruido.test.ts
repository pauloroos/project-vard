import { describe, it, expect } from "vitest";
import { simplex2 } from "../src/ui/ruido";

describe("simplex2", () => {
  it("é determinístico", () => {
    expect(simplex2(1.234, 5.678)).toBe(simplex2(1.234, 5.678));
    expect(simplex2(-3.1, 0.4)).toBe(simplex2(-3.1, 0.4));
  });
  it("fica em [-1, 1] e não é constante", () => {
    let min = 2, max = -2;
    for (let x = -20; x < 20; x += 0.37) {
      for (let y = -20; y < 20; y += 0.41) {
        const v = simplex2(x, y);
        expect(v).toBeGreaterThanOrEqual(-1);
        expect(v).toBeLessThanOrEqual(1);
        min = Math.min(min, v); max = Math.max(max, v);
      }
    }
    expect(max - min).toBeGreaterThan(1);
  });
  it("é contínuo: vizinhos a 0,01 diferem menos de 0,2", () => {
    for (let x = -10; x < 10; x += 0.173) {
      for (let y = -10; y < 10; y += 0.191) {
        const v = simplex2(x, y);
        expect(Math.abs(simplex2(x + 0.01, y) - v)).toBeLessThan(0.2);
        expect(Math.abs(simplex2(x, y + 0.01) - v)).toBeLessThan(0.2);
      }
    }
  });
});
