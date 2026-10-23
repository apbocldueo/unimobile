import { uiText } from "@/shared/i18n";
import { parseStudioFlowDocument, type StudioCapabilityNode, type StudioFlowDocument } from "@/entities/agent-graph";
import type { JsonValue } from "@/shared/lib";
import { assertSecretRefSafe } from "./llmDependencies";

export type RawFieldOwner = {
  canvasId: string;
  candidate: number;
  implementation: string;
  property: "params" | "dependencies";
};
export type RawField = RawFieldOwner & { text: string; error: string | null };
export type EditSnapshot = {
  sessionId: number;
  generation: number;
  baseRevisionId: string | null;
  document: StudioFlowDocument;
};

/** Identify a field by its exact owner, never by a translated label.
 * Args: owner identifies the node, candidate, implementation and property.
 * Returns: An unambiguous local-only registry key.
 */
export function rawFieldKey(owner: RawFieldOwner): string {
  return JSON.stringify([owner.canvasId, owner.candidate, owner.implementation, owner.property]);
}

/** Build the stable implementation identity used to detect owner replacement. */
export function candidateIdentity(node: StudioCapabilityNode, index: number): string {
  const ref = node.implementation.candidates[index];
  return ref ? JSON.stringify([ref.namespace, ref.name, ref.version]) : "";
}

/** Compare JSON values without making object key order a semantic edit.
 * Args: left and right are serializable values.
 * Returns: Whether their recursively ordered representations match.
 */
export function sameJson(left: unknown, right: unknown): boolean {
  return JSON.stringify(ordered(left)) === JSON.stringify(ordered(right));
}

/** Normalize only object key order for local equality; never defines graph identity. */
function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, ordered(v)]));
  }
  return value;
}

/** Parse safe object input without exposing source text in errors.
 * Args: text is transient user input.
 * Raises: A fixed, credential-safe diagnostic on malformed or unsafe input.
 * Returns: A parsed JSON object passing existing credential rules.
 */
export function parseRawObject(text: string): Record<string, JsonValue> {
  let value: unknown;
  try { value = JSON.parse(text); } catch { throw new Error(uiText("JSON 格式错误，请检查括号、引号和逗号。")); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(uiText("配置必须是 JSON 对象。"));
  try { assertSecretRefSafe(value); } catch { throw new Error(uiText("凭证字段必须使用 SecretRef，不能保存真实凭证。")); }
  return value as Record<string, JsonValue>;
}

/** Resolve an exact raw-field owner or reject stale ownership.
 * Returns: The matching candidate from the supplied document.
 * Raises: A safe error if a node or implementation has been replaced.
 */
export function fieldCandidate(document: StudioFlowDocument, owner: RawFieldOwner) {
  const node = document.capabilities.find((item) => item.canvasId === owner.canvasId);
  if (!node || candidateIdentity(node, owner.candidate) !== owner.implementation) throw new Error(uiText("配置所属组件已变化，请重新选择组件。"));
  return node.implementation.candidates[owner.candidate]!;
}

/** Prepare all buffers atomically without mutating the original document.
 * Args: document is the parsed draft; fields are session-owned raw edits.
 * Raises: A fixed structure/safety diagnostic, never user text.
 * Returns: A validated formal document, including every current field.
 */
export function materializeFields(document: StudioFlowDocument, fields: Record<string, RawField>): StudioFlowDocument {
  const copy = parseStudioFlowDocument(document);
  for (const field of Object.values(fields)) fieldCandidate(copy, field)[field.property] = parseRawObject(field.text);
  try {
    assertSecretRefSafe(copy);
    return parseStudioFlowDocument(copy);
  } catch { throw new Error(uiText("文档结构或凭证引用无效，请检查当前配置。")); }
}
