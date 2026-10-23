import { describe, expect, it } from "vitest";
import { configDefaults } from "./configDefaults";

describe("component config defaults", () => {
  it("materializes only Catalog-declared top-level defaults", () => {
    expect(configDefaults({
      type: "object",
      properties: {
        preset: { type: "string", default: "general_vlm_type" },
        retries: { type: "integer", default: 2 },
        prompt_file: { type: "string" },
        nested: { type: "object", default: { mode: "safe" } },
      },
    })).toEqual({ preset: "general_vlm_type", retries: 2, nested: { mode: "safe" } });
  });

  it("returns an empty object for schemas without properties", () => {
    expect(configDefaults({ type: "object" })).toEqual({});
  });
});
