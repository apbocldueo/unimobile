import { cloneJson, isRecord, rejectUnknownKeys, requireString, type JsonValue } from "@/shared/lib";

export type CapabilityFamily =
  | "perception"
  | "planner"
  | "reasoning"
  | "memory"
  | "action_executor"
  | "verifier"
  | "grounder"
  | "tool";
export type CatalogPlacement =
  | "agent_capability"
  | "dependency_only"
  | "runtime_internal"
  | "benchmark_only";

export type ContractPort = {
  id: string;
  direction: "input" | "output";
  dataTypes: string[];
  required: boolean;
  cardinality: "single" | "multiple";
};

export type ComponentCatalogItem = {
  identifier: string;
  namespace: string;
  name: string;
  version: string;
  providerId: string;
  contract: {
    ref: { id: string; version: string };
    ports: ContractPort[];
    adapter: string;
    sideEffect: string;
    idempotent: boolean;
  };
  category: string;
  role?: string;
  placement?: CatalogPlacement;
  capabilityFamily?: CapabilityFamily;
  termination?: Record<string, JsonValue>;
  configSchema: Record<string, JsonValue>;
  dependencySlots: ComponentDependencySlot[];
  availability: {
    available: boolean;
    extra: string;
    errorType: string;
  };
  capabilities: Record<string, JsonValue>;
  provenance: Record<string, JsonValue>;
  display: {
    label: string;
    group: string;
    icon?: string;
  };
};

export type ComponentDependencySlot = {
  name: string;
  required: boolean;
  acceptedNamespaces: string[];
  acceptedCategories: string[];
  configSchema: Record<string, JsonValue>;
};

export type ComponentCatalog = {
  schemaVersion: 1;
  catalogVersion: string;
  components: ComponentCatalogItem[];
  capabilityFamilies?: {
    family: CapabilityFamily;
    label: string;
    extension: boolean;
    availableImplementationCount: number;
  }[];
  diagnostics: unknown[];
};

function parsePort(value: unknown, path: string): ContractPort {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  const direction = value.direction;
  const cardinality = value.cardinality;
  if (direction !== "input" && direction !== "output") {
    throw new Error(`${path}.direction is unsupported`);
  }
  if (cardinality !== "single" && cardinality !== "multiple") {
    throw new Error(`${path}.cardinality is unsupported`);
  }
  if (!Array.isArray(value.data_types)) throw new Error(`${path}.data_types must be an array`);
  return {
    id: requireString(value.id, `${path}.id`),
    direction,
    dataTypes: value.data_types.map((item, index) =>
      requireString(item, `${path}.data_types[${index}]`),
    ),
    required: value.required === true,
    cardinality,
  };
}

function parseComponent(value: unknown, index: number): ComponentCatalogItem {
  const path = `components[${index}]`;
  if (!isRecord(value) || !isRecord(value.contract) || !isRecord(value.contract.ref)) {
    throw new Error(`${path} must contain a contract`);
  }
  if (!Array.isArray(value.contract.ports)) throw new Error(`${path}.contract.ports must be an array`);
  if (!isRecord(value.availability)) throw new Error(`${path}.availability must be an object`);
  if (!isRecord(value.display)) throw new Error(`${path}.display must be an object`);
  const placements = new Set<CatalogPlacement>([
    "agent_capability",
    "dependency_only",
    "runtime_internal",
    "benchmark_only",
  ]);
  const families = new Set<CapabilityFamily>([
    "perception",
    "planner",
    "reasoning",
    "memory",
    "action_executor",
    "verifier",
    "grounder",
    "tool",
  ]);
  if (typeof value.placement !== "string" || !placements.has(value.placement as CatalogPlacement)) {
    throw new Error(`${path}.placement is unsupported`);
  }
  if (
    value.capabilityFamily !== undefined &&
    (typeof value.capabilityFamily !== "string" ||
      !families.has(value.capabilityFamily as CapabilityFamily))
  ) {
    throw new Error(`${path}.capabilityFamily is unsupported`);
  }
  return {
    identifier: requireString(value.identifier, `${path}.identifier`),
    namespace: requireString(value.namespace, `${path}.namespace`),
    name: requireString(value.name, `${path}.name`),
    version: requireString(value.version, `${path}.version`),
    providerId: requireString(value.providerId, `${path}.providerId`),
    contract: {
      ref: {
        id: requireString(value.contract.ref.id, `${path}.contract.ref.id`),
        version: requireString(value.contract.ref.version, `${path}.contract.ref.version`),
      },
      ports: value.contract.ports.map((port, portIndex) =>
        parsePort(port, `${path}.contract.ports[${portIndex}]`),
      ),
      adapter: requireString(value.contract.adapter, `${path}.contract.adapter`),
      sideEffect: requireString(value.contract.side_effect, `${path}.contract.side_effect`),
      idempotent: value.contract.idempotent === true,
    },
    category: requireString(value.category, `${path}.category`),
    ...(typeof value.role === "string" ? { role: value.role } : {}),
    placement: value.placement as CatalogPlacement,
    ...(typeof value.capabilityFamily === "string"
      ? { capabilityFamily: value.capabilityFamily as CapabilityFamily }
      : {}),
    ...(isRecord(value.termination)
      ? { termination: cloneJson(value.termination, `${path}.termination`) as Record<string, JsonValue> }
      : {}),
    configSchema: cloneJson(value.configSchema ?? {}, `${path}.configSchema`) as Record<
      string,
      JsonValue
    >,
    dependencySlots: Array.isArray(value.dependencySlots)
      ? value.dependencySlots.map((slot, slotIndex) => {
          const slotPath = `${path}.dependencySlots[${slotIndex}]`;
          if (!isRecord(slot)) throw new Error(`${slotPath} must be an object`);
          if (!Array.isArray(slot.acceptedNamespaces) || !Array.isArray(slot.acceptedCategories)) {
            throw new Error(`${slotPath} constraints must be arrays`);
          }
          return {
            name: requireString(slot.name, `${slotPath}.name`),
            required: slot.required === true,
            acceptedNamespaces: slot.acceptedNamespaces.map((item, itemIndex) =>
              requireString(item, `${slotPath}.acceptedNamespaces[${itemIndex}]`),
            ),
            acceptedCategories: slot.acceptedCategories.map((item, itemIndex) =>
              requireString(item, `${slotPath}.acceptedCategories[${itemIndex}]`),
            ),
            configSchema: cloneJson(slot.configSchema ?? {}, `${slotPath}.configSchema`) as Record<
              string,
              JsonValue
            >,
          };
        })
      : [],
    availability: {
      available: value.availability.available === true,
      extra: typeof value.availability.extra === "string" ? value.availability.extra : "",
      errorType:
        typeof value.availability.errorType === "string" ? value.availability.errorType : "",
    },
    capabilities: cloneJson(value.capabilities ?? {}, `${path}.capabilities`) as Record<
      string,
      JsonValue
    >,
    provenance: cloneJson(value.provenance ?? {}, `${path}.provenance`) as Record<
      string,
      JsonValue
    >,
    display: {
      label: requireString(value.display.label, `${path}.display.label`),
      group: requireString(value.display.group, `${path}.display.group`),
      ...(typeof value.display.icon === "string" ? { icon: value.display.icon } : {}),
    },
  };
}

/** Parse the safe versioned Component Catalog without executing components. */
export function parseComponentCatalog(value: unknown): ComponentCatalog {
  if (!isRecord(value) || value.schemaVersion !== 1 || !Array.isArray(value.components)) {
    throw new Error("Component Catalog response is invalid");
  }
  if (!Array.isArray(value.capabilityFamilies)) {
    throw new Error("Component Catalog capabilityFamilies are invalid");
  }
  const families = value.capabilityFamilies.map((item, index) => {
    const path = `capabilityFamilies[${index}]`;
    if (!isRecord(item)) throw new Error(`${path} must be an object`);
    rejectUnknownKeys(
      item,
      ["family", "label", "extension", "availableImplementationCount"],
      path,
    );
    const family = requireString(item.family, `${path}.family`) as CapabilityFamily;
    if (![
      "perception", "planner", "reasoning", "memory", "action_executor", "verifier", "grounder", "tool",
    ].includes(family)) throw new Error(`${path}.family is unsupported`);
    const count = item.availableImplementationCount;
    if (!Number.isInteger(count) || (count as number) < 0) {
      throw new Error(`${path}.availableImplementationCount must be a non-negative integer`);
    }
    return {
      family,
      label: requireString(item.label, `${path}.label`),
      extension: item.extension === true,
      availableImplementationCount: count as number,
    };
  });
  return {
    schemaVersion: 1,
    catalogVersion: requireString(value.catalogVersion, "catalogVersion"),
    components: value.components.map(parseComponent),
    capabilityFamilies: families,
    diagnostics: Array.isArray(value.diagnostics) ? [...value.diagnostics] : [],
  };
}
