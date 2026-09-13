import type { ComponentCatalog, ComponentCatalogItem } from "@/entities/component-catalog";
import type { StudioCapabilityNode, StudioFlowDocument } from "@/entities/agent-graph";
import type { JsonValue } from "@/shared/lib";

export type LlmDependencyReference = {
  namespace: string;
  name: string;
  version: string;
  params: Record<string, JsonValue>;
};

const SECRET_KEY = /(?:^|_)(?:api_key|access_token|auth_token|password|secret|secret_key)$/i;
const SECRET_REF = /^[A-Za-z][A-Za-z0-9_.-]{0,127}$/;

/** Reject raw credentials before they enter capability implementation dependencies. */
export function assertSecretRefSafe(value: unknown, path = "dependencies"): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertSecretRefSafe(item, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (SECRET_KEY.test(key)) {
      const valid = Boolean(
        item && typeof item === "object" && !Array.isArray(item) &&
        Object.keys(item).length === 1 &&
        SECRET_REF.test(String((item as { secret_ref?: unknown }).secret_ref ?? "")),
      );
      if (!valid) throw new Error(`${path}.${key} 必须使用 SecretRef，不能保存 raw secret。`);
    }
    assertSecretRefSafe(item, `${path}.${key}`);
  }
}

/** Resolve the exact Catalog descriptor for one implementation candidate. */
export function descriptorForCandidate(
  candidate: { namespace: string; name: string; version?: string },
  catalog: ComponentCatalog | null,
): ComponentCatalogItem | undefined {
  return catalog?.components.find(
    (item) => item.namespace === candidate.namespace && item.name === candidate.name && item.version === candidate.version,
  );
}

/** Report whether one implementation formally accepts a dependency-only LLM. */
export function acceptsLlmDependency(
  component: ComponentCatalogItem | undefined,
  llm: ComponentCatalogItem,
): boolean {
  const slot = component?.dependencySlots.find((item) => item.name === "llm");
  return Boolean(slot) && llm.placement === "dependency_only" &&
    (!slot!.acceptedNamespaces.length || slot!.acceptedNamespaces.includes(llm.namespace)) &&
    (!slot!.acceptedCategories.length || slot!.acceptedCategories.includes(llm.category));
}

function updateNode(
  node: StudioCapabilityNode,
  catalog: ComponentCatalog,
  llm: ComponentCatalogItem,
  reference: LlmDependencyReference,
  missingOnly: boolean,
): { node: StudioCapabilityNode; count: number } {
  let count = 0;
  const candidates = node.implementation.candidates.map((candidate) => {
    if (!acceptsLlmDependency(descriptorForCandidate(candidate, catalog), llm)) return candidate;
    if (missingOnly && candidate.dependencies.llm !== undefined) return candidate;
    count += 1;
    return {
      ...candidate,
      dependencies: {
        ...candidate.dependencies,
        llm: { namespace: reference.namespace, name: reference.name, version: reference.version, params: { ...reference.params } },
      },
    };
  });
  return { node: { ...node, implementation: { ...node.implementation, candidates } }, count };
}

function applyLlmDependency(
  document: StudioFlowDocument,
  catalog: ComponentCatalog,
  reference: LlmDependencyReference,
  missingOnly: boolean,
): { document: StudioFlowDocument; changedCandidates: number } {
  const llm = catalog.components.find(
    (item) => item.namespace === reference.namespace && item.name === reference.name && item.version === reference.version,
  );
  if (!llm || llm.placement !== "dependency_only") throw new Error("选择的 LLM 不是当前 Catalog 的 dependency-only 实现。");
  assertSecretRefSafe(reference.params, "llm.params");
  let changedCandidates = 0;
  const capabilities = document.capabilities.map((node) => {
    const updated = updateNode(node, catalog, llm, reference, missingOnly);
    changedCandidates += updated.count;
    return updated.node;
  });
  return { document: { ...document, capabilities }, changedCandidates };
}

/** Apply one explicit LLM dependency to every compatible capability implementation. */
export function applyLlmDependencyToCompatibleCandidates(
  document: StudioFlowDocument,
  catalog: ComponentCatalog,
  reference: LlmDependencyReference,
) {
  return applyLlmDependency(document, catalog, reference, false);
}

/** Fill only absent required LLM dependency slots. */
export function applyLlmDependencyToMissingCandidates(
  document: StudioFlowDocument,
  catalog: ComponentCatalog,
  reference: LlmDependencyReference,
) {
  return applyLlmDependency(document, catalog, reference, true);
}

/** List dependency-only LLM providers compatible with an absent required slot. */
export function availableLlmProvidersForMissingCandidates(
  document: StudioFlowDocument,
  catalog: ComponentCatalog,
): ComponentCatalogItem[] {
  const missing = document.capabilities.flatMap((node) =>
    node.implementation.candidates.flatMap((candidate) => {
      const descriptor = descriptorForCandidate(candidate, catalog);
      return candidate.dependencies.llm === undefined && descriptor?.dependencySlots.some((slot) => slot.name === "llm" && slot.required)
        ? [descriptor]
        : [];
    }),
  );
  return catalog.components.filter(
    (provider) => provider.availability.available && provider.placement === "dependency_only" &&
      missing.some((component) => acceptsLlmDependency(component, provider)),
  );
}

/** Count superseded OpenAI API-key SecretRef identities in capability dependencies. */
export function countLegacyOpenAiSecretRefs(document: StudioFlowDocument): number {
  return document.capabilities.reduce((count, node) => count + node.implementation.candidates.filter((candidate) => {
    const llm = candidate.dependencies.llm;
    return Boolean(
      llm && typeof llm === "object" && !Array.isArray(llm) &&
      llm.params && typeof llm.params === "object" && !Array.isArray(llm.params) &&
      llm.params.api_key && typeof llm.params.api_key === "object" && !Array.isArray(llm.params.api_key) &&
      llm.params.api_key.secret_ref === "openai_api_key",
    );
  }).length, 0);
}

/** Align only the superseded API-key identity while preserving all other dependencies. */
export function alignLegacyOpenAiSecretRefs(
  document: StudioFlowDocument,
): { document: StudioFlowDocument; changedCandidates: number } {
  let changedCandidates = 0;
  const capabilities = document.capabilities.map((node) => ({
    ...node,
    implementation: {
      ...node.implementation,
      candidates: node.implementation.candidates.map((candidate) => {
        const llm = candidate.dependencies.llm;
        if (!llm || typeof llm !== "object" || Array.isArray(llm) ||
          !llm.params || typeof llm.params !== "object" || Array.isArray(llm.params) ||
          !llm.params.api_key || typeof llm.params.api_key !== "object" || Array.isArray(llm.params.api_key) ||
          llm.params.api_key.secret_ref !== "openai_api_key") return candidate;
        changedCandidates += 1;
        return {
          ...candidate,
          dependencies: {
            ...candidate.dependencies,
            llm: {
              ...llm,
              params: {
                ...llm.params,
                api_key: { secret_ref: "api_key" },
                ...(llm.params.base_url === undefined ? { base_url: { secret_ref: "base_url" } } : {}),
              },
            },
          },
        };
      }),
    },
  }));
  return { document: { ...document, capabilities }, changedCandidates };
}
