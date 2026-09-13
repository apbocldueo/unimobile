import { studioRequest } from "@/shared/api";
import { parseComponentCatalog, type ComponentCatalog } from "../model/catalog.schema";

/** Load the authoritative authoring Catalog from the local Studio backend. */
export async function fetchComponentCatalog(): Promise<ComponentCatalog> {
  return parseComponentCatalog(await studioRequest("/studio/components/catalog"));
}
