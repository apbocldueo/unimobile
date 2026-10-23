import { describe, expect, it } from "vitest";
import { DEFAULT_PANES, fitPanes, parsePanePreferences } from "./panePreferences";

describe("display-only pane preferences", () => {
  it("rejects malformed, unknown version and nonnumeric widths", () => {
    for (const value of [null, "{", "null", '{"version":2}', '{"version":1,"palette":"wide","inspector":360}']) expect(parsePanePreferences(value)).toEqual(DEFAULT_PANES);
  });
  it("bounds persisted numbers without importing other fields", () => {
    expect(parsePanePreferences('{"version":1,"palette":-1,"inspector":9999,"document":{"secret":"ignored"}}')).toEqual({ palette: 140, inspector: 720 });
  });
  it("fits measured workspace widths including zoomed narrow layouts", () => {
    for (const width of [240, 450, 800, 900, 1024, 1280, 1440]) {
      const panes = fitPanes(width, { palette: 360, inspector: 720 });
      expect(panes.palette + panes.inspector + 12).toBeLessThan(width);
      expect(panes.palette).toBeGreaterThan(0);
      expect(panes.inspector).toBeGreaterThan(0);
    }
  });
});
