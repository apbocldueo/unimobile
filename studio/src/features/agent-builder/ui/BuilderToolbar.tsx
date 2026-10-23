import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  compileStudioDocument,
  parseStudioFlowDocument,
  type StudioFlowDocument,
} from "@/entities/agent-graph";
import { createStudioAgent } from "@/entities/agent";
import { getAgentRevision } from "@/entities/agent-revision";
import { runtimeConfigurationLabel, runtimeReadinessKeys, useRuntimeEnvironmentReadiness, type RuntimeEnvironmentReadiness } from "@/entities/runtime-readiness";
import { useToastStore } from "@/stores/toastStore";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { useSaveAgentRevisionCommand } from "../model/useSaveAgentRevisionCommand";
import { materializeFields, type EditSnapshot } from "../model/editSession";
import { sameSemanticContent } from "../model/editHistory";
import { useBuilderPanels } from "./BuilderPanelContext";
import { BuilderHistoryControls } from "./BuilderHistoryControls";
import styles from "./agentBuilder.module.css";

type BuilderToolbarProps = {
  agentName: string;
  catalogVersion: string | undefined;
  onReload: () => Promise<void>;
};

export type BuilderCommandId =
  | "validate"
  | "save"
  | "run"
  | "save_as"
  | "import"
  | "export"
  | "load_revision"
  | "reset";

/** Stable affordance hierarchy without changing command handlers or gates. */
export const BUILDER_COMMAND_PRIORITY: Readonly<Record<BuilderCommandId, "primary" | "secondary">> = {
  validate: "primary",
  save: "primary",
  run: "primary",
  save_as: "secondary",
  import: "secondary",
  export: "secondary",
  load_revision: "secondary",
  reset: "secondary",
};

function safeFileName(name: string): string {
  return name.replace(/[<>:"/\\|?*]/g, "_").slice(0, 80) || "agent";
}

function downloadDocument(studioDocument: StudioFlowDocument): void {
  const blob = new Blob([JSON.stringify(studioDocument, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeFileName(studioDocument.name)}.studio-v2.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Render document actions and static configuration status, without implying live connectivity.
 * Args: agentName and catalogVersion identify the draft; onReload handles explicit reload.
 * Returns: Save/run controls and navigation to the independent checks panel.
 */
export function BuilderToolbar({
  agentName,
  catalogVersion,
  onReload,
}: BuilderToolbarProps) {
  useUiLocale();
  const navigate = useNavigate();
  const panels = useBuilderPanels();
  const queryClient = useQueryClient();
  const pushToast = useToastStore((state) => state.pushToast);
  const document = useAgentBuilderDocumentStore((state) => state.document);
  const dirty = useAgentBuilderDocumentStore((state) => state.dirty);
  const layoutOnlyDirty = useAgentBuilderDocumentStore((state) => {
    if (!state.dirty || !state.document) return false;
    try { return sameSemanticContent(materializeFields(state.document, state.rawFields), state.baseline); }
    catch { return false; }
  });
  const baseRevisionId = useAgentBuilderDocumentStore((state) => state.baseRevisionId);
  const compileResult = useAgentBuilderDocumentStore((state) => state.compileResult);
  const conflictRevisionId = useAgentBuilderDocumentStore((state) => state.conflictRevisionId);
  const setCompileResult = useAgentBuilderDocumentStore((state) => state.setCompileResult);
  const importDocument = useAgentBuilderDocumentStore((state) => state.importDocument);
  const resetToBaseline = useAgentBuilderDocumentStore((state) => state.resetToBaseline);
  const hydrate = useAgentBuilderDocumentStore((state) => state.hydrate);
  const fileRef = useRef<HTMLInputElement>(null);
  const runtimeReadiness = useRuntimeEnvironmentReadiness();
  const savePending = useAgentBuilderDocumentStore((state) => state.savePending);
  const inputError = useAgentBuilderDocumentStore((state) => state.inputError);
  const saveAsOwners = useRef(new WeakSet<EditSnapshot>());
  const emptyDraft = Boolean(document && document.capabilities.length === 0);

  /** Prepare all current fields before a command; never fall back to old parsed values. */
  const withSnapshot = (command: (snapshot: EditSnapshot) => void) => {
    try { command(useAgentBuilderDocumentStore.getState().prepareSnapshot()); }
    catch (error) { pushToast({ message: error instanceof Error ? error.message : uiText("配置无效。"), tone: "error" }); }
  };

  const validateMutation = useMutation({
    mutationFn: async (snapshot: EditSnapshot & { validationId: number }) => {
      if (!useAgentBuilderDocumentStore.getState().matchesValidationSnapshot(snapshot)) throw new Error(uiText("编辑内容已变化，请重新校验。"));
      return compileStudioDocument(snapshot.document, catalogVersion);
    },
    onSuccess: (result, snapshot) => {
      const state = useAgentBuilderDocumentStore.getState();
      if (!state.matchesValidationSnapshot(snapshot) || state.validationId !== snapshot.validationId) return;
      setCompileResult(result);
      pushToast({
        message: result.isSuccess
          ? uiText("流程检查通过，可以保存或准备试跑。")
          : uiMessage`校验完成：${result.summary.errorCount} 个错误`,
        tone: result.isSuccess ? "success" : "warning",
        durationMs: 5200,
      });
    },
    onError: (error, snapshot) => {
      const state = useAgentBuilderDocumentStore.getState();
      if (state.matchesValidationSnapshot(snapshot) && state.validationId === snapshot.validationId) {
        pushToast({ message: error instanceof Error ? error.message : uiText("校验失败"), tone: "error" });
      }
    },
  });

  const saveMutation = useSaveAgentRevisionCommand();

  const saveAsMutation = useMutation({
    mutationFn: async (snapshot: EditSnapshot) => {
      if (!useAgentBuilderDocumentStore.getState().matchesSnapshot(snapshot)) throw new Error(uiText("编辑内容已变化，请重新另存。"));
      if (useAgentBuilderDocumentStore.getState().savePending) throw new Error(uiText("已有保存正在进行。"));
      const name = window.prompt(uiText("新 Agent 名称"), `${snapshot.document.name} Copy`)?.trim();
      if (!name) throw new Error(uiText("已取消 Save As"));
      useAgentBuilderDocumentStore.setState({ savePending: true });
      saveAsOwners.current.add(snapshot);
      return createStudioAgent(name, { ...snapshot.document, name });
    },
    onSuccess: async (result, snapshot) => {
      await queryClient.invalidateQueries({ queryKey: ["studio-agents"] });
      if (!useAgentBuilderDocumentStore.getState().matchesSnapshot(snapshot)) return;
      pushToast({ message: uiText("已创建独立 Agent 与初始 revision"), tone: "success" });
      const path = `/agents/${encodeURIComponent(result.agent.agentId)}/design`;
      useAgentBuilderDocumentStore.setState({ departurePath: path });
      navigate(path);
    },
    onError: (error, snapshot) => {
      if (!useAgentBuilderDocumentStore.getState().matchesSnapshot(snapshot)) return;
      if (error instanceof Error && error.message === uiText("已取消 Save As")) return;
      pushToast({ message: error instanceof Error ? error.message : uiText("Save As 失败"), tone: "error" });
    },
    onSettled: (_result, _error, snapshot) => {
      if (saveAsOwners.current.has(snapshot) && useAgentBuilderDocumentStore.getState().sessionId === snapshot.sessionId) useAgentBuilderDocumentStore.setState({ savePending: false });
      saveAsOwners.current.delete(snapshot);
    },
  });

  const loadRevisionMutation = useMutation({
    mutationFn: async (owner: { sessionId: number; generation: number }) => {
      const state = useAgentBuilderDocumentStore.getState();
      if (state.sessionId !== owner.sessionId || state.generation !== owner.generation) throw new Error(uiText("编辑会话已变化"));
      if (!state.document) throw new Error(uiText("Agent document 尚未加载"));
      if (state.dirty && !window.confirm(uiText("Load revision 会放弃当前未保存修改，是否继续？"))) {
        throw new Error(uiText("已取消 Load revision"));
      }
      const revisionId = window.prompt("Revision ID", baseRevisionId ?? "")?.trim();
      if (!revisionId) throw new Error(uiText("已取消 Load revision"));
      return { revision: await getAgentRevision(state.document.agentId, revisionId), sessionId: state.sessionId, generation: state.generation };
    },
    onSuccess: ({ revision, sessionId, generation }) => {
      const state = useAgentBuilderDocumentStore.getState();
      if (state.sessionId !== sessionId) return;
      if (state.generation !== generation) {
        pushToast({ message: uiText("加载期间有新编辑，未替换草稿。请重新选择加载。"), tone: "warning" });
        return;
      }
      hydrate(revision);
      pushToast({
        message: uiMessage`已加载 immutable revision ${revision.ordinal}`,
        tone: "success",
      });
    },
    onError: (error, owner) => {
      const state = useAgentBuilderDocumentStore.getState();
      if (state.sessionId !== owner.sessionId || state.generation !== owner.generation) return;
      if (error instanceof Error && error.message === uiText("已取消 Load revision")) return;
      pushToast({
        message: error instanceof Error ? error.message : uiText("Revision 加载失败"),
        tone: "error",
      });
    },
  });

  /** Validate a complete import before asking to replace; throws without changing the session. */
  const importRaw = async (raw: unknown) => {
    if (!document || !raw || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error(uiText("JSON root 必须是对象"));
    }
    const record = raw as Record<string, unknown>;
    if (record.schemaVersion === 1) {
      throw new Error(uiText("旧版 Schema 1 仅可读取与导出；请使用当前能力组件重新搭建后再运行。"));
    }
    const parsed = materializeFields(parseStudioFlowDocument(record), {});
    if (useAgentBuilderDocumentStore.getState().dirty && !window.confirm(uiText("导入会替换当前未保存内容，是否继续？"))) return;
    importDocument(
      {
        ...parsed,
        agentId: document.agentId,
        documentId: document.documentId,
      },
    );
    pushToast({ message: uiText("Schema 3 能力文档已导入当前草稿"), tone: "success" });
  };

  const runtimeDiagnostic = runtimeReadiness.data?.diagnostics[0]?.message;
  const runDisabled =
    !document
    || !baseRevisionId
    || Boolean(conflictRevisionId)
    || savePending
    || Boolean(inputError)
    || runtimeReadiness.isLoading
    || runtimeReadiness.isError
    || runtimeReadiness.data?.ready !== true
    || (!dirty && compileResult?.isSuccess !== true)
    || (dirty && compileResult?.isSuccess === false);

  /** Open launch mode only for a verified immutable revision. */
  const openRunLaunch = async () => {
    if (!document || runDisabled) return;
    let prepared: EditSnapshot;
    try { prepared = useAgentBuilderDocumentStore.getState().prepareSnapshot(); } catch { return; }
    if (!useAgentBuilderDocumentStore.getState().dirty) {
      navigate(
        `/agents/${encodeURIComponent(document.agentId)}/run?revisionId=${encodeURIComponent(baseRevisionId!)}`,
      );
      return;
    }
    try {
      const { revision, snapshot } = await saveMutation.mutateAsync({
        document,
        baseRevisionId,
        snapshot: prepared,
      });
      const readiness = queryClient.getQueryState<RuntimeEnvironmentReadiness>(runtimeReadinessKeys.process);
      if (revision.compileSnapshot.status !== "valid" || !useAgentBuilderDocumentStore.getState().matchesSnapshot(snapshot) || readiness?.status !== "success" || readiness.data?.ready !== true) return;
      navigate(
        `/agents/${encodeURIComponent(revision.agentId)}/run?revisionId=${encodeURIComponent(revision.revisionId)}`,
      );
    } catch {
      // The shared save command already surfaced conflict or transport failure.
    }
  };
  return (
    <header className={styles.toolbar}>
      <div className={styles.toolbarSummary}>
        <strong>{dirty ? layoutOnlyDirty ? uiText("布局有未保存修改") : uiText("草稿有未保存修改") : uiText("已保存")}</strong>
      </div>
      <BuilderHistoryControls />
      {inputError || (compileResult && !compileResult.isSuccess && !emptyDraft) ? (
        <button type="button" className={`${styles.statusBadge} ${styles.statusInvalid} ${styles.statusLink}`} onClick={() => panels.show("checks")}>
          {inputError ? uiText("配置输入有错误") : uiMessage`${compileResult?.summary.errorCount ?? 0} 项待修复`}
        </button>
      ) : null}
      <button
        type="button"
        data-command-priority={BUILDER_COMMAND_PRIORITY.validate}
        className={styles.button}
        disabled={validateMutation.isPending}
        onClick={() => { panels.show("checks"); withSnapshot((snapshot) => {
          const validationId = useAgentBuilderDocumentStore.getState().validationId + 1;
          useAgentBuilderDocumentStore.setState({ validationId });
          validateMutation.mutate({ ...snapshot, validationId });
        }); }}
      >
        {validateMutation.isPending ? uiText("检查中…") : uiText("检查流程")}
      </button>
      <button
        type="button"
        data-command-priority={BUILDER_COMMAND_PRIORITY.save}
        className={styles.button}
        disabled={!dirty || savePending || Boolean(inputError) || Boolean(conflictRevisionId)}
        onClick={() => {
          withSnapshot((snapshot) => saveMutation.mutate({ document: snapshot.document, baseRevisionId: snapshot.baseRevisionId, snapshot }));
        }}
      >
        {saveMutation.isPending ? uiText("保存中…") : uiText("保存")}
      </button>
      <button
        type="button"
        data-command-priority={BUILDER_COMMAND_PRIORITY.run}
        className={`${styles.button} ${styles.buttonPrimary}`}
        disabled={runDisabled}
        title={
          conflictRevisionId
            ? uiText("先解决 revision 冲突")
            : compileResult?.isSuccess === false
              ? uiText("当前 revision 校验失败")
              : runtimeDiagnostic ?? (runtimeReadiness.isLoading ? uiText("正在读取运行配置") : uiText("进入任务准备页，提交任务后才会运行"))
        }
        onClick={() => void openRunLaunch()}
      >
        {saveMutation.isPending
          ? uiText("保存中…")
          : dirty
            ? uiText("保存并试跑")
            : uiText("试跑")}
      </button>
      <details className={styles.moreMenu}>
        <summary className={styles.button}>{uiText("更多操作")}</summary>
        <div className={styles.moreMenuPanel}>
          <button type="button" className={styles.menuButton} onClick={() => panels.show("checks")}>{uiText("查看检查结果")}</button>
          <button type="button" className={styles.menuButton} onClick={() => navigate("/settings")}>
            {uiText("运行设置 ·")}{" "}{runtimeConfigurationLabel(runtimeReadiness.data, runtimeReadiness.isError, runtimeReadiness.isFetching)}
          </button>
          <p>{uiText("文档与版本")}</p>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.save_as}
            className={styles.menuButton}
            disabled={savePending}
            onClick={() => withSnapshot((snapshot) => saveAsMutation.mutate(snapshot))}
          >
            {uiText("另存为")}</button>
          <button type="button" data-command-priority={BUILDER_COMMAND_PRIORITY.import} className={styles.menuButton} onClick={() => fileRef.current?.click()}>
            {uiText("导入")}</button>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.export}
            className={styles.menuButton}
            disabled={!document}
            onClick={() => {
              withSnapshot((snapshot) => downloadDocument(snapshot.document));
            }}
          >
            {uiText("导出")}</button>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.load_revision}
            className={styles.menuButton}
            disabled={loadRevisionMutation.isPending}
            onClick={() => {
              const { sessionId, generation } = useAgentBuilderDocumentStore.getState();
              loadRevisionMutation.mutate({ sessionId, generation });
            }}
          >
            {loadRevisionMutation.isPending ? uiText("加载中…") : uiText("加载历史版本")}
          </button>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.reset}
            className={`${styles.menuButton} ${styles.menuButtonDanger}`}
            disabled={!dirty}
            onClick={() => {
              if (window.confirm(uiText("放弃当前未保存修改并恢复已保存 revision？"))) resetToBaseline();
            }}
          >
            {uiText("放弃修改")}</button>
          <details className={styles.technicalDetails}>
            <summary>{uiText("技术详情")}</summary>
            <span title={uiText("静态配置检查，不代表设备在线或模型连接成功")}>{runtimeConfigurationLabel(runtimeReadiness.data, runtimeReadiness.isError, runtimeReadiness.isFetching)}</span>
            <span>Agent</span>
            <code>{agentName}</code>
            <span>Revision</span>
            <code>{baseRevisionId ?? "unsaved"}</code>
          </details>
        </div>
      </details>
      <input
        ref={fileRef}
        hidden
        type="file"
        accept="application/json,.json"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          const origin = useAgentBuilderDocumentStore.getState();
          void file
            .text()
            .then((text) => {
              const current = useAgentBuilderDocumentStore.getState();
              if (current.sessionId !== origin.sessionId || current.generation !== origin.generation) return;
              return importRaw(JSON.parse(text) as unknown);
            })
            .catch(() => {
              if (useAgentBuilderDocumentStore.getState().sessionId !== origin.sessionId) return;
              pushToast({
                message: uiText("导入失败：文件格式、结构或凭证引用无效。原有编辑未被替换。"),
                tone: "error",
                durationMs: 6500,
              });
            });
        }}
      />
      {conflictRevisionId ? (
        <div className={styles.conflict}>
          {uiText("远端已到")}{" "}{conflictRevisionId.slice(0, 12)}
          <button
            type="button"
            className={styles.button}
            onClick={() => void onReload()}
          >
            Reload remote
          </button>
        </div>
      ) : null}
    </header>
  );
}
