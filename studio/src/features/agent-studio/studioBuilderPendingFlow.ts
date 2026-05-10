import type { FlowDocumentV1 } from "@/modules/flow-graph/flowDocument";
import { tryParseFlowDocument } from "@/modules/flow-graph/flowDocument";

const SESSION_KEY = "zx-studio-builder-pending-flow-json-v1";

/**
 * 在跳转到 `/builder` 之前写入；画布挂载后由 `takeStudioBuilderPendingFlowDocument` 读取并清除。
 * 用于开始页弹窗、将来「保存并打开」等场景。
 */
export function setStudioBuilderPendingFlowDocument(doc: FlowDocumentV1): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(doc));
  } catch {
    /* quota / private */
  }
}

/** 读取并移除；若无合法数据返回 `null`。 */
export function takeStudioBuilderPendingFlowDocument(): FlowDocumentV1 | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(SESSION_KEY);
    const parsed = tryParseFlowDocument(raw);
    return parsed.ok ? parsed.doc : null;
  } catch {
    return null;
  }
}
