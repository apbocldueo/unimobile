export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

/** Return whether an unknown value is a non-array object. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Parse a required string at one human-readable field path. */
export function requireString(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${path} must be a non-empty string`);
  }
  return value;
}

/** Parse a required finite number at one human-readable field path. */
export function requireNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${path} must be a finite number`);
  }
  return value;
}

/** Clone JSON data after rejecting functions, objects and non-finite values. */
export function cloneJson(value: unknown, path = "value"): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error(`${path} must be finite`);
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => cloneJson(item, `${path}[${index}]`));
  }
  if (isRecord(value)) {
    const output: Record<string, JsonValue> = {};
    for (const [key, item] of Object.entries(value)) {
      output[key] = cloneJson(item, `${path}.${key}`);
    }
    return output;
  }
  throw new Error(`${path} must contain JSON values only`);
}

/** Assert that an object contains no fields beyond the declared contract. */
export function rejectUnknownKeys(
  value: Record<string, unknown>,
  allowed: readonly string[],
  path: string,
): void {
  const allowedSet = new Set(allowed);
  const unexpected = Object.keys(value).find((key) => !allowedSet.has(key));
  if (unexpected) throw new Error(`${path}.${unexpected} is not supported`);
}
