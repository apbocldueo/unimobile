import type { StudioFlowDocument } from "@/entities/agent-graph";
import { sameJson, type RawField } from "./editSession";

export type HistoryEntry = {
  document: StudioFlowDocument;
  rawFields: Record<string, RawField>;
  selectedCanvasId: string | null;
  selectedEdgeId: string | null;
};

export const HISTORY_LIMIT = 50;
export const HISTORY_BYTE_LIMIT = 4 * 1024 * 1024;

/** Compare editable content excluding presentation; this is not a canonical hash.
 * Args: left/right are strictly parsed documents or absent baselines.
 * Returns: Whether presentation-only changes leave the compared content equal.
 */
export function sameSemanticContent(left: StudioFlowDocument | null, right: StudioFlowDocument | null): boolean {
  if (!left || !right) return left === right;
  return sameJson({ ...left, presentation: null }, { ...right, presentation: null });
}

/** Append an immutable checkpoint with bounded count and approximate UTF-16 bytes.
 * Args: entries is one history direction; entry is the current editor checkpoint.
 * Returns: An oldest-to-newest window retaining the newest entries; oversized entries clear the direction.
 */
export function appendHistory(entries: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  const result = [...entries, entry].slice(-HISTORY_LIMIT);
  let bytes = 0;
  for (let index = result.length - 1; index >= 0; index -= 1) {
    bytes += JSON.stringify(result[index]).length * 2;
    if (bytes > HISTORY_BYTE_LIMIT) return result.slice(index + 1);
  }
  return result;
}
