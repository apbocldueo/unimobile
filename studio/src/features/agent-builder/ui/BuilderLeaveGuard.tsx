import { uiText, useUiLocale } from "@/shared/i18n";
import { useContext, useEffect, useRef, useState } from "react";
import { UNSAFE_DataRouterContext, useBlocker } from "react-router-dom";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { useSaveAgentRevisionCommand } from "../model/useSaveAgentRevisionCommand";
import styles from "./agentBuilder.module.css";

/** Mount routed protection only in a data router; isolated legacy render tests remain usable. */
export function BuilderLeaveGuard() {
  useUiLocale();
  const router = useContext(UNSAFE_DataRouterContext);
  return router ? <RoutedLeaveGuard /> : null;
}

/** Protect the captured destination and keep failed or superseded saves in the editor. */
function RoutedLeaveGuard() {
  useUiLocale();
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    const state = useAgentBuilderDocumentStore.getState();
    return state.dirty && currentLocation.pathname !== nextLocation.pathname && state.departurePath !== nextLocation.pathname;
  });
  const inputError = useAgentBuilderDocumentStore((state) => state.inputError);
  const pending = useAgentBuilderDocumentStore((state) => state.savePending);
  const conflict = useAgentBuilderDocumentStore((state) => state.conflictRevisionId);
  const save = useSaveAgentRevisionCommand();
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    if (blocker.state === "blocked") {
      setMessage(null);
      if (dialog.current?.showModal && !dialog.current.open) dialog.current.showModal();
      cancel.current?.focus();
    }
  }, [blocker.state]);
  if (blocker.state !== "blocked") return null;

  /** Save the prepared session and proceed only if no subsequent edit changed its meaning. */
  const saveAndLeave = async () => {
    const state = useAgentBuilderDocumentStore.getState();
    if (!state.document || state.savePending) return;
    try {
      const prepared = state.prepareSnapshot();
      const { snapshot } = await save.mutateAsync({ document: prepared.document, baseRevisionId: prepared.baseRevisionId, snapshot: prepared });
      const current = useAgentBuilderDocumentStore.getState();
      if (current.matchesSnapshot(snapshot) && !current.dirty) blocker.proceed();
      else setMessage(uiText("已有更新的编辑未保存，请继续编辑或重新保存。"));
    } catch { setMessage(uiText("未能确认保存成功，编辑内容已保留。请处理错误或冲突后重试。")); }
  };

  return (
    <dialog ref={dialog} aria-labelledby="builder-leave-heading" className={styles.leaveDialog}
      onCancel={(event) => { event.preventDefault(); if (!pending) blocker.reset(); }}>
      <h2 id="builder-leave-heading">{uiText("有未保存的编辑")}</h2>
      <p>{uiText("离开会丢弃当前未保存的图和配置输入。")}</p>
      {inputError ? <p role="alert">{inputError} {" "}{uiText("请返回修正后再保存。")}</p> : null}
      {conflict ? <p role="alert">{uiText("存在保存冲突，请返回处理，或明确放弃当前编辑。")}</p> : null}
      {message ? <p role="alert">{message}</p> : null}
      <div className={styles.leaveActions}>
        <button ref={cancel} type="button" className={styles.button} disabled={pending} onClick={() => blocker.reset()}>{uiText("继续编辑")}</button>
        <button type="button" className={styles.button} disabled={pending} onClick={() => blocker.proceed()}>{uiText("放弃修改并离开")}</button>
        <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} disabled={pending || Boolean(inputError) || Boolean(conflict)} onClick={() => void saveAndLeave()}>{pending ? uiText("正在保存…") : uiText("保存并离开")}</button>
      </div>
    </dialog>
  );
}
