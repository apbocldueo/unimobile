import type {
  ComponentCatalog,
  ComponentCatalogItem,
  CapabilityFamily,
} from "@/entities/component-catalog";
import type {
  StudioCapabilityNode,
  StudioFlowDocument,
} from "@/entities/agent-graph";
import { nextStableId } from "./flowAdapter";

/** Return exact currently eligible implementations for one Palette family. */
export function implementationsForFamily(
  catalog: ComponentCatalog,
  family: CapabilityFamily,
): ComponentCatalogItem[] {
  return catalog.components.filter(
    (item) =>
      item.placement === "agent_capability" &&
      item.capabilityFamily === family &&
      item.availability.available,
  );
}

/** Build one capability instance from backend-authoritative family metadata. */
export function createCapabilityNode(
  family: CapabilityFamily,
  catalog: ComponentCatalog,
  document: StudioFlowDocument,
): StudioCapabilityNode {
  const component = implementationsForFamily(catalog, family)[0];
  if (!component) throw new Error(`能力 ${family} 当前没有可用实现`);
  const existingLogical = document.capabilities.map((node) => node.logicalId);
  const existingCanvas = [
    document.input.canvasId,
    document.output.canvasId,
    ...document.capabilities.map((node) => node.canvasId),
  ];
  const logicalId = nextStableId(family, existingLogical);
  const canvasId = nextStableId(`node_${logicalId}`, existingCanvas);
  return {
    canvasId,
    logicalId,
    family,
    lifecycle: family === "planner" ? "on_run_start" : family === "memory" ? "stateful" : "per_step",
    primary: family === "action_executor",
    implementation: {
      policy: "single",
      candidates: [{
        namespace: component.namespace,
        name: component.name,
        version: component.version,
        params: {},
        dependencies: {},
      }],
    },
  };
}
