import type { StudioCapabilityFamily, StudioFlowDocument } from "@/entities/agent-graph";

export type CanvasPosition = { x: number; y: number };

const LAYER_X_START = 80;
const COLUMN_GAP = 100;
const NODE_GAP = 70;
type NodeSize = { width: number; height: number };

/** Return the visual lane used for a graph object without changing graph semantics.
 * Args: object is a boundary or capability from the authoring document.
 * Returns: A lane offset where negative values sit above the main flow and positive values sit below it.
 */
function layoutLane(object: { kind?: "input" | "output"; family?: StudioCapabilityFamily }): number {
  if (object.kind === "input" || object.kind === "output") return 0;
  if (object.family === "perception") return -1;
  if (object.family === "memory" || object.family === "grounder" || object.family === "tool") return 1;
  return 0;
}

/** Compute deterministic presentation positions from ordinary graph flow.
 * Args: document is the current capability document; sizes contains measured or conservative expanded bounds. Feedback edges are return paths.
 * Returns: Every boundary/capability canvas ID mapped to a finite position. Ordinary relations determine horizontal layers; perception and state/tool nodes use separate visual lanes so return paths remain legible.
 */
export function autoLayoutPositions(document: StudioFlowDocument, sizes: Record<string, NodeSize> = {}): Record<string, CanvasPosition> {
  const objects = [document.input, ...document.capabilities, document.output];
  const order = new Map(objects.map((object, index) => [object.logicalId, index]));
  const outgoing = new Map<string, string[]>();
  const indegree = new Map(objects.map((object) => [object.logicalId, 0]));

  for (const relation of document.relations) {
    if (relation.kind === "feedback") continue;
    const source = relation.source.ownerId;
    const target = relation.target.ownerId;
    if (!indegree.has(source) || !indegree.has(target) || source === target) continue;
    const targets = outgoing.get(source) ?? [];
    if (targets.includes(target)) continue;
    targets.push(target);
    targets.sort((left, right) => (order.get(left) ?? 0) - (order.get(right) ?? 0));
    outgoing.set(source, targets);
    indegree.set(target, (indegree.get(target) ?? 0) + 1);
  }

  const layers = new Map<string, number>([[document.input.logicalId, 0]]);
  const ready = objects
    .filter((object) => (indegree.get(object.logicalId) ?? 0) === 0)
    .map((object) => object.logicalId)
    .sort((left, right) => (order.get(left) ?? 0) - (order.get(right) ?? 0));
  const processed = new Set<string>();

  while (ready.length) {
    const current = ready.shift()!;
    if (processed.has(current)) continue;
    processed.add(current);
    const currentLayer = layers.get(current) ?? 0;
    layers.set(current, currentLayer);
    for (const target of outgoing.get(current) ?? []) {
      layers.set(target, Math.max(layers.get(target) ?? 0, currentLayer + 1));
      const remaining = (indegree.get(target) ?? 0) - 1;
      indegree.set(target, remaining);
      if (remaining === 0) ready.push(target);
    }
    ready.sort((left, right) => (order.get(left) ?? 0) - (order.get(right) ?? 0));
  }

  const highestCapabilityLayer = Math.max(
    0,
    ...document.capabilities.map((node) => layers.get(node.logicalId) ?? 0),
  );
  layers.set(document.output.logicalId, Math.max(layers.get(document.output.logicalId) ?? 0, highestCapabilityLayer + 1));

  let fallbackLayer = highestCapabilityLayer + 1;
  for (const object of objects) {
    if (!layers.has(object.logicalId)) {
      fallbackLayer += 1;
      layers.set(object.logicalId, fallbackLayer);
    }
  }

  const buckets = new Map<number, string[]>();
  for (const object of objects) {
    const layer = layers.get(object.logicalId) ?? 0;
    const bucket = buckets.get(layer) ?? [];
    bucket.push(object.logicalId);
    buckets.set(layer, bucket);
  }

  const positions: Record<string, CanvasPosition> = {};
  const byLogical = new Map(objects.map((object) => [object.logicalId, object]));
  /** Use finite positive geometry, including for not-yet-measured or malformed cards. */
  const sizeOf = (logicalId: string): NodeSize => {
    const object = byLogical.get(logicalId)!;
    const given = sizes[object.canvasId];
    const fallback = "family" in object ? { width: 250, height: 320 } : { width: 100, height: 50 };
    return {
      width: given && Number.isFinite(given.width) && given.width > 0 ? given.width : fallback.width,
      height: given && Number.isFinite(given.height) && given.height > 0 ? given.height : fallback.height,
    };
  };
  /** Reserve enough vertical room for the tallest stack in a visual lane. */
  const laneHeight = (lane: number) => Math.max(0, ...[...buckets.values()].map((ids) =>
    ids.filter((id) => layoutLane(byLogical.get(id)!) === lane)
      .reduce((total, id) => total + sizeOf(id).height + NODE_GAP, 0)));
  const laneStart = new Map([[-1, 80], [0, 80 + laneHeight(-1)], [1, 80 + laneHeight(-1) + laneHeight(0)]]);
  let columnX = LAYER_X_START;
  for (const [, ids] of [...buckets.entries()].sort(([left], [right]) => left - right)) {
    ids.sort((left, right) => {
      const leftObject = objects.find((item) => item.logicalId === left);
      const rightObject = objects.find((item) => item.logicalId === right);
      const laneDifference = layoutLane(leftObject ?? {}) - layoutLane(rightObject ?? {});
      return laneDifference || (order.get(left) ?? 0) - (order.get(right) ?? 0);
    });
    const laneOffsets = new Map<number, number>();
    ids.forEach((logicalId) => {
      const object = objects.find((item) => item.logicalId === logicalId);
      if (!object) return;
      const lane = layoutLane(object);
      const laneOffset = laneOffsets.get(lane) ?? 0;
      laneOffsets.set(lane, laneOffset + sizeOf(logicalId).height + NODE_GAP);
      positions[object.canvasId] = {
        x: columnX,
        y: (laneStart.get(lane) ?? 80) + laneOffset,
      };
    });
    columnX += Math.max(...ids.map((id) => sizeOf(id).width)) + COLUMN_GAP;
  }
  return positions;
}
