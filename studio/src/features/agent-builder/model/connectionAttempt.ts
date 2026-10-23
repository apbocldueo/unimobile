import { uiText } from "@/shared/i18n";
import type { Connection, FinalConnectionState } from "@xyflow/react";

export type AttemptHandle = { nodeId: string; id?: string | null; type: "source" | "target" };

/** Recover rejected endpoints because XYFlow may clear an invalid toHandle.
 * Args: event/state describe the gesture; clickStart supplies click-only starting state.
 * Returns: An oriented attempt, a direction error, or null for release on empty space.
 */
export function endedConnection(event: MouseEvent | TouchEvent, state: FinalConnectionState, clickStart?: AttemptHandle): Connection | string | null {
  const from = state.fromHandle ?? clickStart;
  if (!from) return null;
  let to: AttemptHandle | null = state.toHandle;
  if (!to) {
    const point = "changedTouches" in event ? event.changedTouches[0] : event;
    const element = event.target instanceof Element && event.target.closest("[data-handleid][data-nodeid]") ? event.target : point && typeof document.elementFromPoint === "function"
      ? document.elementFromPoint(point.clientX, point.clientY) : event.target;
    const handle = element instanceof Element ? element.closest<HTMLElement>("[data-handleid][data-nodeid]") : null;
    if (handle) {
      const nodeId = handle.dataset.nodeid;
      const id = handle.dataset.handleid;
      const type = handle.classList.contains("source") ? "source" : "target";
      if (nodeId && id) to = { ...from, nodeId, id, type };
    }
  }
  if (!to) return null;
  if (from.nodeId === to.nodeId && from.id === to.id && from.type === to.type) return null;
  if (from.type === to.type) return uiText("请把输出端口连接到输入端口。");
  const [source, target] = from.type === "source" ? [from, to] : [to, from];
  return { source: source.nodeId, sourceHandle: source.id ?? null, target: target.nodeId, targetHandle: target.id ?? null };
}
