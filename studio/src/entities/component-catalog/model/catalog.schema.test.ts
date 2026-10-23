import { describe, expect, it } from "vitest";
import { parseComponentCatalog } from "./catalog.schema";

describe("parseComponentCatalog", () => {
  it("normalizes contract snake-case fields into the frontend DTO", () => {
    const catalog = parseComponentCatalog({
      schemaVersion: 1,
      catalogVersion: "sha256:test",
      capabilityFamilies: [],
      components: [
        {
          identifier: "agent.reasoning:demo@1",
          namespace: "agent.reasoning",
          name: "demo",
          version: "1",
          providerId: "test",
          placement: "agent_capability",
          capabilityFamily: "reasoning",
          termination: null,
          contract: {
            ref: { id: "zhixing.core.reasoning", version: "1.0" },
            ports: [
              {
                id: "task",
                direction: "input",
                data_types: ["task_input"],
                required: true,
                cardinality: "single",
              },
            ],
            adapter: "core_role",
            side_effect: "none",
            idempotent: true,
          },
          category: "core_agent",
          configSchema: { type: "object", properties: {} },
          dependencySlots: [{
            name: "llm",
            required: true,
            acceptedNamespaces: ["llm"],
            acceptedCategories: ["runtime_service"],
            configSchema: { type: "object" },
          }],
          availability: { available: true, extra: "", errorType: "" },
          capabilities: {},
          provenance: {},
          display: { label: "Demo", group: "reasoning" },
        },
      ],
      diagnostics: [],
    });
    expect(catalog.components[0]?.contract.ports[0]?.dataTypes).toEqual(["task_input"]);
    expect(catalog.components[0]?.contract.sideEffect).toBe("none");
    expect(catalog.components[0]?.dependencySlots[0]?.name).toBe("llm");
  });

  it("rejects malformed dependency-slot constraint metadata", () => {
    expect(() => parseComponentCatalog({
      schemaVersion: 1,
      catalogVersion: "sha256:test",
      capabilityFamilies: [],
      components: [{
        identifier: "agent.reasoning:demo@1",
        namespace: "agent.reasoning",
        name: "demo",
        version: "1",
        providerId: "test",
        placement: "agent_capability",
        capabilityFamily: "reasoning",
        termination: null,
        contract: {
          ref: { id: "zhixing.core.reasoning", version: "1.0" },
          ports: [],
          adapter: "core_role",
          side_effect: "none",
          idempotent: true,
        },
        category: "core_agent",
        configSchema: {},
        dependencySlots: [{
          name: "llm",
          required: true,
          acceptedNamespaces: "llm",
          acceptedCategories: [],
          configSchema: {},
        }],
        availability: { available: true },
        capabilities: {},
        provenance: {},
        display: { label: "Demo", group: "reasoning" },
      }],
      diagnostics: [],
    })).toThrow(/constraints/);
  });
});
