import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ComponentCatalog } from "@/entities/component-catalog";
import type { JsonValue } from "@/shared/lib";
import { LlmDependencyForm } from "./LlmDependencyForm";

const catalog: ComponentCatalog = {
  schemaVersion: 1,
  catalogVersion: "catalog",
  diagnostics: [],
  capabilityFamilies: [],
  components: [{
    identifier: "llm:openai_llm@1",
    namespace: "llm",
    name: "openai_llm",
    version: "1",
    providerId: "fixture",
    placement: "dependency_only",
    category: "runtime_service",
    contract: { ref: { id: "llm", version: "1.0" }, ports: [], adapter: "runtime_service", sideEffect: "network", idempotent: false },
    configSchema: {
      type: "object",
      properties: {
        api_key: { type: "object", properties: { secret_ref: { type: "string" } }, "x-zhixing-secret-ref": true },
        model: { type: "string", default: "gpt-4o" },
        temperature: { type: "number", minimum: 0, maximum: 2, default: 0.1 },
        max_tokens: { type: "integer", minimum: 1, default: 4096 },
      },
    },
    dependencySlots: [],
    availability: { available: true, extra: "", errorType: "" },
    capabilities: {},
    provenance: {},
    display: { label: "OpenAI LLM", group: "llm" },
  }],
};

const slot = { name: "llm", required: true, acceptedNamespaces: ["llm"], acceptedCategories: ["runtime_service"], configSchema: {} };

afterEach(() => cleanup());

describe("LlmDependencyForm", () => {
  it("guides provider, model, and SecretRef configuration without accepting a raw key", () => {
    let value: JsonValue | undefined;
    const view = render(<LlmDependencyForm slot={slot} catalog={catalog} value={value} onChange={(next) => { value = next; }} />);
    fireEvent.change(screen.getByLabelText("模型提供方"), { target: { value: "llm:openai_llm@1" } });
    view.rerender(<LlmDependencyForm slot={slot} catalog={catalog} value={value} onChange={(next) => { value = next; }} />);
    fireEvent.change(screen.getByLabelText("模型 ID"), { target: { value: "gpt-4.1-mini" } });
    view.rerender(<LlmDependencyForm slot={slot} catalog={catalog} value={value} onChange={(next) => { value = next; }} />);
    fireEvent.change(screen.getByLabelText("API 凭证 SecretRef"), { target: { value: "openai_api_key" } });
    expect(value).toEqual({
      namespace: "llm",
      name: "openai_llm",
      version: "1",
      params: { model: "gpt-4.1-mini", api_key: { secret_ref: "openai_api_key" } },
    });
    expect(JSON.stringify(value)).not.toContain("sk-");
    expect(screen.getByText(/只填写 SecretRef 名称/)).not.toBeNull();
  });

  it("keeps advanced extension values while editing a typed scalar", () => {
    const value: JsonValue = {
      namespace: "llm", name: "openai_llm", version: "1",
      params: { model: "gpt-4o", custom_extension: { mode: "json" } },
    };
    let nextValue = value as Record<string, JsonValue>;
    const view = render(<LlmDependencyForm slot={slot} catalog={catalog} value={nextValue} onChange={(next) => { nextValue = next as Record<string, JsonValue>; }} />);
    fireEvent.change(screen.getByLabelText("温度"), { target: { value: "0.4" } });
    view.rerender(<LlmDependencyForm slot={slot} catalog={catalog} value={nextValue} onChange={(next) => { nextValue = next as Record<string, JsonValue>; }} />);
    expect(nextValue).toEqual({
      namespace: "llm", name: "openai_llm", version: "1",
      params: { model: "gpt-4o", custom_extension: { mode: "json" }, temperature: 0.4 },
    });
  });
});
