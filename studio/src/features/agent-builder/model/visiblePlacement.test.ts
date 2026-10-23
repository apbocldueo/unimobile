import { describe, expect, it } from "vitest";
import { visiblePlacement } from "./visiblePlacement";

describe("visible node placement", () => {
  const size = { width: 220, height: 160 };
  it.each([0.2, 1, 2])("uses the translated flow viewport at zoom %s", (zoom) => {
    const visible = { x: -3200 / zoom, y: 1500 / zoom, width: 960 / zoom, height: 600 / zoom };
    const point = visiblePlacement(visible, size, []);
    expect(point).not.toBeNull();
    expect(point!.x).toBeGreaterThanOrEqual(visible.x);
    expect(point!.y).toBeGreaterThanOrEqual(visible.y);
    expect(point!.x + size.width).toBeLessThanOrEqual(visible.x + visible.width);
    expect(point!.y + size.height).toBeLessThanOrEqual(visible.y + visible.height);
  });
  it("uses the latest occupied boxes for consecutive additions without moving them", () => {
    const visible = { x: 0, y: 0, width: 1200, height: 800 };
    const first = visiblePlacement(visible, size, [])!;
    const occupied = [{ ...first, ...size }];
    const before = JSON.stringify(occupied);
    expect(visiblePlacement(visible, size, occupied)).not.toEqual(first);
    expect(JSON.stringify(occupied)).toBe(before);
  });
  it("retains the interaction corner in an undersized viewport", () => {
    expect(visiblePlacement({ x: 13, y: 27, width: 80, height: 60 }, size, []))
      .toEqual({ x: 13, y: 27 });
  });
  it("falls back to a visible point when the region is fully occupied", () => {
    const visible = { x: 0, y: 0, width: 300, height: 200 };
    expect(visiblePlacement(visible, size, [visible])).toEqual({ x: 40, y: 20 });
  });
  it.each([0, -1, NaN, Infinity])("rejects an unmeasurable width %s", (width) => {
    expect(visiblePlacement({ x: 0, y: 0, width, height: 500 }, size, [])).toBeNull();
  });
});
