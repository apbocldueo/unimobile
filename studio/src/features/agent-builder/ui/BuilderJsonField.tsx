import { uiText, useUiLocale } from "@/shared/i18n";
import { useContext, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { QueryClientContext } from "@tanstack/react-query";
import { rawFieldKey, type RawFieldOwner } from "../model/editSession";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { useSaveAgentRevisionCommand } from "../model/useSaveAgentRevisionCommand";
import styles from "./agentBuilder.module.css";

/** Save the same prepared session from the dialog; errors never dismiss its draft. */
function ExpandedSave() {
  useUiLocale();
  const save = useSaveAgentRevisionCommand();
  const dirty = useAgentBuilderDocumentStore((state) => state.dirty);
  const pending = useAgentBuilderDocumentStore((state) => state.savePending);
  const conflict = useAgentBuilderDocumentStore((state) => state.conflictRevisionId);
  const [message, setMessage] = useState("");
  /** Prepare all fields, including the focused editor, at the existing save boundary. */
  const submit = async () => {
    try {
      setMessage("");
      const snapshot = useAgentBuilderDocumentStore.getState().prepareSnapshot();
      await save.mutateAsync({ document: snapshot.document, baseRevisionId: snapshot.baseRevisionId, snapshot });
      setMessage(uiText("版本已保存；后续修改仍需再次保存。"));
    } catch { setMessage(uiText("未能保存。请检查配置输入、连接或版本冲突；编辑已保留。")); }
  };
  return <>
    {message ? <p role="status">{message}</p> : null}
    {conflict ? <p role="alert">{uiText("存在版本冲突。关闭编辑器后可重新加载或另存；当前输入会保留。")}</p> : null}
    <button type="button" className={styles.button} disabled={!dirty || pending || Boolean(conflict)} onClick={() => void submit()}>{pending ? uiText("正在保存…") : uiText("保存")}</button>
  </>;
}

/** Two presentation sizes for one session-owned raw field; no modal copy exists.
 * Args: owner is the exact candidate/property identity; value is its parsed baseline.
 * Returns: An inline editor or a modal editor preserving the same raw buffer.
 */
export function BuilderJsonField({ label, value, owner }: { label: string; value: unknown; owner: RawFieldOwner }) {
  useUiLocale();
  const key = rawFieldKey(owner);
  const field = useAgentBuilderDocumentStore((state) => state.rawFields[key]);
  const focusField = useAgentBuilderDocumentStore((state) => state.focusField);
  const editRaw = useAgentBuilderDocumentStore((state) => state.editRaw);
  const sessionId = useAgentBuilderDocumentStore((state) => state.sessionId);
  const [expanded, setExpanded] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  const query = useContext(QueryClientContext);
  useEffect(() => { setExpanded(false); }, [sessionId, key]);
  useEffect(() => {
    if (expanded) {
      const element = dialog.current;
      const returnTarget = trigger.current;
      element?.showModal();
      ref.current?.focus();
      return () => {
        const restore = element?.contains(document.activeElement);
        element?.close();
        if (restore) {
          if (returnTarget?.isConnected) returnTarget.focus();
          else document.querySelector<HTMLElement>('[aria-label="Builder workspace"]')?.focus();
        }
      };
    }
  }, [expanded]);
  useEffect(() => {
    if (focusField === key) ref.current?.focus();
    else if (focusField && expanded) setExpanded(false); // Let the authoritative error target receive focus.
  }, [focusField, key, expanded]);
  /** Closing changes only presentation; malformed text is deliberately retained. */
  const close = () => { dialog.current?.close(); setExpanded(false); trigger.current?.focus(); };
  /** Keep Tab within the editor; native browser chrome can otherwise take focus. */
  const trapFocus = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== "Tab") return;
    const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')];
    const first = controls[0];
    const last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  };
  const editor = <>
    <label htmlFor={id}>{label}</label>
    <textarea id={id} ref={ref} aria-label={label} aria-invalid={Boolean(field?.error)} aria-describedby={field?.error ? `${id}-error` : undefined}
      className={styles.textarea} spellCheck={false} value={field?.text ?? JSON.stringify(value, null, 2)}
      onChange={(event) => editRaw(owner, event.target.value)}
      onBlur={() => {
        const state = useAgentBuilderDocumentStore.getState();
        state.finishHistoryGroup();
        if (Object.values(state.rawFields).some((entry) => entry.error)) return;
        try { state.prepareSnapshot(); } catch { /* Existing preparation owns safe diagnostics. */ }
      }} />
    {field?.error ? <span id={`${id}-error`} role="alert" className={styles.errorText}>{field.error}</span> : null}
  </>;
  return <div className={styles.field}>
    <button ref={trigger} type="button" className={styles.expandEditorButton} aria-label={`Expand ${label}`} onClick={() => setExpanded(true)}>Expand editor ↗</button>
    {!expanded ? editor : <dialog ref={dialog} className={styles.configDialog} aria-labelledby={`${id}-heading`}
      onKeyDown={trapFocus} onCancel={(event) => { event.preventDefault(); close(); }}>
      <div className={styles.dialogHeading}><h2 id={`${id}-heading`}>Edit configuration</h2><button type="button" className={styles.button} onClick={close}>Close</button></div>
      <p className={styles.muted}>{uiText("输入保留在当前草稿中。关闭不会丢弃编辑；保存 才会保存到服务端。")}</p>
      <div className={styles.expandedField}>{editor}</div>
      <div className={styles.dialogFooter}>{query ? <ExpandedSave key={`${sessionId}:${key}`} /> : null}</div>
    </dialog>}
  </div>;
}
