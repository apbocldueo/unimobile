import { describe, expect, it } from "vitest";
import type { ComponentCatalog } from "@/entities/component-catalog";
import { palettePortPreview } from "./palettePreview";

const catalog = {
  schemaVersion: 1,
  catalogVersion: "test",
  diagnostics: [],
  components: [
    {
      identifier: "test.reasoning@1",
      namespace: "test",
      name: "reasoning",
      version: "1",
      providerId: "test",
      contract: { ref: { id: "test.reasoning", version: "1" }, ports: [
        { id: "task", direction: "input", dataTypes: ["task_input"], required: true, cardinality: "single" },
        { id: "action", direction: "output", dataTypes: ["action"], required: true, cardinality: "single" },
      ], adapter: "test", sideEffect: "none", idempotent: true },
      category: "core_agent",
      placement: "agent_capability",
      capabilityFamily: "reasoning",
      configSchema: {},
      dependencySlots: [],
      availability: { available: true, extra: "", errorType: "" },
      capabilities: {},
      provenance: {},
      display: { label: "Reasoning", group: "core" },
    },
  ],
} as ComponentCatalog;

describe("palettePortPreview", () => {
  it("previews available family ports without duplicates", () => {
    const preview = palettePortPreview(catalog, "reasoning");
    expect(preview.inputs.map((port) => port.id)).toEqual(["task"]);
    expect(preview.outputs.map((port) => port.id)).toEqual(["action"]);
  });

  it("returns an empty preview when the family has no available implementation", () => {
    expect(palettePortPreview(catalog, "memory")).toEqual({ inputs: [], outputs: [] });
  });
});
