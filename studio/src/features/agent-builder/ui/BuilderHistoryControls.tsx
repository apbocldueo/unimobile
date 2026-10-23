import { uiText, useUiLocale } from "@/shared/i18n";
import { useEffect } from "react";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import styles from "./agentBuilder.module.css";

/** Handle history inside this workspace while leaving native text and modal editing alone.
 * Args: event is a bubbling key event; ownsBodyFocus covers a removed focused node/control.
 * Returns: Nothing; only recognized workspace history commands are consumed.
 */
function handleBuilderHistoryKey(event: KeyboardEvent, ownsBodyFocus: boolean): void {
  const target = event.target;
  if (event.defaultPrevented || event.isComposing || event.altKey || !(target instanceof Element)) return;
  const inWorkspace = target.closest('[aria-label="Builder workspace"]') || (target === document.body && ownsBodyFocus);
  if (!inWorkspace || target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="dialog"], dialog')) return;
  if (!event.metaKey && !event.ctrlKey) return;
  const key = event.key.toLowerCase();
  const undo = key === "z" && !event.shiftKey;
  const redo = (key === "z" && event.shiftKey) || (key === "y" && event.ctrlKey && !event.metaKey);
  if (!undo && !redo) return;
  event.preventDefault();
  const state = useAgentBuilderDocumentStore.getState();
  if (undo) state.undo(); else state.redo();
}

/** Expose bounded session history through buttons and scoped keyboard commands. */
export function BuilderHistoryControls() {
  useUiLocale();
  const canUndo = useAgentBuilderDocumentStore((state) => state.past.length > 0);
  const canRedo = useAgentBuilderDocumentStore((state) => state.future.length > 0);
  useEffect(() => {
    let ownsBodyFocus = false;
    /** Retain workspace ownership when deleting focus; outside interaction relinquishes it. */
    const rememberScope = (event: Event) => {
      if (event.type === "focusin" && event.target === document.body) return;
      ownsBodyFocus = event.target instanceof Element && Boolean(event.target.closest('[aria-label="Builder workspace"]'));
    };
    /** Dispatch a scoped history command with the last explicit interaction owner. */
    const onKeyDown = (event: KeyboardEvent) => handleBuilderHistoryKey(event, ownsBodyFocus);
    window.addEventListener("pointerdown", rememberScope, true);
    window.addEventListener("focusin", rememberScope, true);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", rememberScope, true);
      window.removeEventListener("focusin", rememberScope, true);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);
  return <div className={styles.historyControls} role="group" aria-label={uiText("编辑历史")}>
    <button type="button" className={styles.button} disabled={!canUndo} title={uiText("撤销（⌘/Ctrl Z）")} onClick={() => useAgentBuilderDocumentStore.getState().undo()}>{uiText("撤销")}</button>
    <button type="button" className={styles.button} disabled={!canRedo} title={uiText("重做（⌘/Ctrl Shift Z；Ctrl Y）")} onClick={() => useAgentBuilderDocumentStore.getState().redo()}>{uiText("重做")}</button>
  </div>;
}
