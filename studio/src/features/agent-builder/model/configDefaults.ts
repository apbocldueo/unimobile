import { isRecord, type JsonValue } from "@/shared/lib";

/** Materialize only Catalog-declared top-level defaults for a component config. */
export function configDefaults(schema: Record<string, JsonValue>): Record<string, JsonValue> {
  if (!isRecord(schema.properties)) return {};
  const defaults: Record<string, JsonValue> = {};
  for (const [name, property] of Object.entries(schema.properties)) {
    if (isRecord(property) && Object.prototype.hasOwnProperty.call(property, "default")) {
      defaults[name] = property.default as JsonValue;
    }
  }
  return defaults;
}
