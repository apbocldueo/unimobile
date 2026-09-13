import { describe, expect, it } from "vitest";
import { AGENT_STUDIO_FLOW_PRESETS } from "./flowPresetDocuments";

describe("local Agent Studio flow fallbacks", () => {
  it("exposes only an honest empty canvas and no runnable linear preset", () => {
    expect(AGENT_STUDIO_FLOW_PRESETS.map((item) => item.id)).toEqual(["empty"]);
    expect(AGENT_STUDIO_FLOW_PRESETS[0]?.build()).toMatchObject({
      schemaVersion: 1,
      nodes: [],
      edges: [],
    });
  });
});
