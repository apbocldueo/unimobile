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
import { useRuntimeEnvironmentReadiness } from "@/entities/runtime-readiness";
import { useToastStore } from "@/stores/toastStore";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { useSaveAgentRevisionCommand } from "../model/useSaveAgentRevisionCommand";
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

/** Render explicit Validate, Save, Save & Run, and document actions. */
export function BuilderToolbar({
  agentName,
  catalogVersion,
  onReload,
}: BuilderToolbarProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const pushToast = useToastStore((state) => state.pushToast);
  const document = useAgentBuilderDocumentStore((state) => state.document);
  const dirty = useAgentBuilderDocumentStore((state) => state.dirty);
  const baseRevisionId = useAgentBuilderDocumentStore((state) => state.baseRevisionId);
  const compileResult = useAgentBuilderDocumentStore((state) => state.compileResult);
  const conflictRevisionId = useAgentBuilderDocumentStore((state) => state.conflictRevisionId);
  const setCompileResult = useAgentBuilderDocumentStore((state) => state.setCompileResult);
  const importDocument = useAgentBuilderDocumentStore((state) => state.importDocument);
  const resetToBaseline = useAgentBuilderDocumentStore((state) => state.resetToBaseline);
  const hydrate = useAgentBuilderDocumentStore((state) => state.hydrate);
  const fileRef = useRef<HTMLInputElement>(null);
  const runtimeReadiness = useRuntimeEnvironmentReadiness();

  const validateMutation = useMutation({
    mutationFn: async () => {
      if (!document) throw new Error("Agent document 尚未加载");
      return compileStudioDocument(document, catalogVersion);
    },
    onSuccess: (result) => {
      setCompileResult(result);
      pushToast({
        message: result.isSuccess
          ? `校验通过：${result.canonicalHash ?? "canonical hash unavailable"}`
          : `校验完成：${result.summary.errorCount} 个错误`,
        tone: result.isSuccess ? "success" : "warning",
        durationMs: 5200,
      });
    },
    onError: (error) =>
      pushToast({ message: error instanceof Error ? error.message : "校验失败", tone: "error" }),
  });

  const saveMutation = useSaveAgentRevisionCommand();

  const saveAsMutation = useMutation({
    mutationFn: async () => {
      if (!document) throw new Error("Agent document 尚未加载");
      const name = window.prompt("新 Agent 名称", `${document.name} Copy`)?.trim();
      if (!name) throw new Error("已取消 Save As");
      return createStudioAgent(name, { ...document, name });
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["studio-agents"] });
      pushToast({ message: "已创建独立 Agent 与初始 revision", tone: "success" });
      navigate(`/agents/${encodeURIComponent(result.agent.agentId)}/design`);
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "已取消 Save As") return;
      pushToast({ message: error instanceof Error ? error.message : "Save As 失败", tone: "error" });
    },
  });

  const loadRevisionMutation = useMutation({
    mutationFn: async () => {
      if (!document) throw new Error("Agent document 尚未加载");
      if (dirty && !window.confirm("Load revision 会放弃当前未保存修改，是否继续？")) {
        throw new Error("已取消 Load revision");
      }
      const revisionId = window.prompt("Revision ID", baseRevisionId ?? "")?.trim();
      if (!revisionId) throw new Error("已取消 Load revision");
      return getAgentRevision(document.agentId, revisionId);
    },
    onSuccess: (revision) => {
      hydrate(revision);
      pushToast({
        message: `已加载 immutable revision ${revision.ordinal}`,
        tone: "success",
      });
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "已取消 Load revision") return;
      pushToast({
        message: error instanceof Error ? error.message : "Revision 加载失败",
        tone: "error",
      });
    },
  });

  const importRaw = async (raw: unknown) => {
    if (!document || !raw || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("JSON root 必须是对象");
    }
    const record = raw as Record<string, unknown>;
    if (record.schemaVersion === 1) {
      throw new Error("旧版 Schema 1 仅可读取与导出；请使用当前能力组件重新搭建后再运行。");
    }
    const parsed = parseStudioFlowDocument(record);
    importDocument(
      {
        ...parsed,
        agentId: document.agentId,
        documentId: document.documentId,
      },
    );
    pushToast({ message: "Schema 3 能力文档已导入当前草稿", tone: "success" });
  };

  const statusClass = compileResult
    ? compileResult.isSuccess
      ? styles.statusValid
      : styles.statusInvalid
    : styles.statusPending;
  const runtimeDiagnostic = runtimeReadiness.data?.diagnostics[0]?.message;
  const runDisabled =
    !document
    || !baseRevisionId
    || Boolean(conflictRevisionId)
    || saveMutation.isPending
    || runtimeReadiness.isLoading
    || runtimeReadiness.isError
    || runtimeReadiness.data?.ready !== true
    || (!dirty && compileResult?.isSuccess !== true)
    || (dirty && compileResult?.isSuccess === false);

  /** Open launch mode only for a verified immutable revision. */
  const openRunLaunch = async () => {
    if (!document || runDisabled) return;
    if (!dirty) {
      navigate(
        `/agents/${encodeURIComponent(document.agentId)}/run?revisionId=${encodeURIComponent(baseRevisionId!)}`,
      );
      return;
    }
    try {
      const { revision } = await saveMutation.mutateAsync({
        document,
        baseRevisionId,
      });
      if (revision.compileSnapshot.status !== "valid") return;
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
        <strong>{dirty ? "草稿有未保存修改" : "当前 revision 已保存"}</strong>
        <small>先校验语义，再保存 immutable revision；满足运行条件后可直接运行。</small>
      </div>
      <span className={`${styles.statusBadge} ${statusClass}`}>
        {compileResult
          ? compileResult.isSuccess
            ? "Graph 已通过"
            : `Graph 有 ${compileResult.summary.errorCount} 个错误`
          : "Graph 待校验"}
      </span>
      {runtimeReadiness.data?.ready ? (
        <span className={`${styles.statusBadge} ${styles.statusValid}`}>运行环境已就绪</span>
      ) : (
        <button
          type="button"
          className={`${styles.statusBadge} ${styles.statusInvalid} ${styles.statusLink}`}
          title={runtimeDiagnostic ?? "前往 Settings 检查 Provider、SecretRef 与设备配置"}
          onClick={() => navigate("/settings")}
        >
          {runtimeReadiness.isLoading ? "正在检查运行环境…" : "运行环境未就绪 · 查看 Settings"}
        </button>
      )}
      <button
        type="button"
        data-command-priority={BUILDER_COMMAND_PRIORITY.validate}
        className={styles.button}
        disabled={validateMutation.isPending}
        onClick={() => validateMutation.mutate()}
      >
        {validateMutation.isPending ? "Validating…" : "Validate"}
      </button>
      <button
        type="button"
        data-command-priority={BUILDER_COMMAND_PRIORITY.save}
        className={`${styles.button} ${styles.buttonPrimary}`}
        disabled={!dirty || saveMutation.isPending}
        onClick={() => {
          if (document) saveMutation.mutate({ document, baseRevisionId });
        }}
      >
        {saveMutation.isPending ? "Saving…" : "Save revision"}
      </button>
      <button
        type="button"
        data-command-priority={BUILDER_COMMAND_PRIORITY.run}
        className={`${styles.button} ${styles.buttonPrimary}`}
        disabled={runDisabled}
        title={
          conflictRevisionId
            ? "先解决 revision 冲突"
            : compileResult?.isSuccess === false
              ? "当前 revision 校验失败"
              : runtimeDiagnostic ?? "正在读取运行环境"
        }
        onClick={() => void openRunLaunch()}
      >
        {saveMutation.isPending
          ? "Saving…"
          : dirty
            ? "Save & Run"
            : "Run"}
      </button>
      <details className={styles.moreMenu}>
        <summary className={styles.button}>更多操作</summary>
        <div className={styles.moreMenuPanel}>
          <p>文档与版本</p>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.save_as}
            className={styles.menuButton}
            disabled={saveAsMutation.isPending}
            onClick={() => saveAsMutation.mutate()}
          >
            Save As
          </button>
          <button type="button" data-command-priority={BUILDER_COMMAND_PRIORITY.import} className={styles.menuButton} onClick={() => fileRef.current?.click()}>
            Import
          </button>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.export}
            className={styles.menuButton}
            disabled={!document}
            onClick={() => {
              if (document) downloadDocument(document);
            }}
          >
            Export
          </button>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.load_revision}
            className={styles.menuButton}
            disabled={loadRevisionMutation.isPending}
            onClick={() => loadRevisionMutation.mutate()}
          >
            {loadRevisionMutation.isPending ? "Loading…" : "Load revision"}
          </button>
          <button
            type="button"
            data-command-priority={BUILDER_COMMAND_PRIORITY.reset}
            className={`${styles.menuButton} ${styles.menuButtonDanger}`}
            disabled={!dirty}
            onClick={() => {
              if (window.confirm("放弃当前未保存修改并恢复已保存 revision？")) resetToBaseline();
            }}
          >
            Reset draft
          </button>
          <details className={styles.technicalDetails}>
            <summary>技术详情</summary>
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
          void file
            .text()
            .then((text) => importRaw(JSON.parse(text) as unknown))
            .catch((error: unknown) =>
              pushToast({
                message: error instanceof Error ? error.message : "导入失败",
                tone: "error",
                durationMs: 6500,
              }),
            );
        }}
      />
      {conflictRevisionId ? (
        <div className={styles.conflict}>
          远端已到 {conflictRevisionId.slice(0, 12)}
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
