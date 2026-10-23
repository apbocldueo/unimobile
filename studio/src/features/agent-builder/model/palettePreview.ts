import type { CapabilityFamily, ComponentCatalog, ContractPort } from "@/entities/component-catalog";

export type PalettePortPreview = {
  inputs: ContractPort[];
  outputs: ContractPort[];
};

/** Collect stable input/output previews from available Catalog implementations.
 * Args: catalog is the backend-authoritative component catalog; family is the capability family; limit bounds each preview list.
 * Returns: Deduplicated ports in Catalog order, limited for compact palette cards.
 */
export function palettePortPreview(
  catalog: ComponentCatalog | null | undefined,
  family: CapabilityFamily,
  limit = 3,
): PalettePortPreview {
  const components = (catalog?.components ?? []).filter(
    (item) => item.placement === "agent_capability" && item.capabilityFamily === family && item.availability.available,
  );
  const collect = (direction: ContractPort["direction"]): ContractPort[] => {
    const seen = new Set<string>();
    return components
      .flatMap((item) => item.contract.ports)
      .filter((port) => port.direction === direction)
      .filter((port) => {
        if (seen.has(port.id)) return false;
        seen.add(port.id);
        return true;
      })
      .slice(0, Math.max(0, limit));
  };
  return { inputs: collect("input"), outputs: collect("output") };
}
