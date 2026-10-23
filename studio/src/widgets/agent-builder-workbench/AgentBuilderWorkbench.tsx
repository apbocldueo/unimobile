import { uiText, useUiLocale } from "@/shared/i18n";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchComponentCatalog } from "@/entities/component-catalog";
import { getStudioAgent } from "@/entities/agent";
import { useToastStore } from "@/stores/toastStore";
import {
  BuilderCanvas,
  AgentBuilderFlowProvider,
  BuilderInspector,
  BuilderPalette,
  BuilderToolbar,
  BuilderLeaveGuard,
  BuilderLayout,
  agentBuilderStyles as styles,
  useAgentBuilderDocumentStore,
} from "@/features/agent-builder";

type AgentBuilderWorkbenchProps = {
  agentId: string;
};

/** Compose remote resources and the local Builder draft into the Stage 1 workbench. */
export function AgentBuilderWorkbench({ agentId }: AgentBuilderWorkbenchProps) {
  useUiLocale();
  const hydrate = useAgentBuilderDocumentStore((state) => state.hydrate);
  const clear = useAgentBuilderDocumentStore((state) => state.clear);
  const loadedAgentId = useAgentBuilderDocumentStore((state) => state.agentId);
  const baseRevisionId = useAgentBuilderDocumentStore((state) => state.baseRevisionId);
  const legacyRevisionId = useAgentBuilderDocumentStore((state) => state.legacyRevisionId);
  const catalogQuery = useQuery({
    queryKey: ["studio-component-catalog"],
    queryFn: fetchComponentCatalog,
  });
  const agentQuery = useQuery({
    queryKey: ["studio-agent", agentId],
    queryFn: () => getStudioAgent(agentId),
  });

  useEffect(() => {
    const revision = agentQuery.data?.currentRevision;
    if (!revision) return;
    if (loadedAgentId !== agentId || baseRevisionId === null) hydrate(revision);
  }, [agentId, agentQuery.data, baseRevisionId, hydrate, loadedAgentId]);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!useAgentBuilderDocumentStore.getState().dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  useEffect(
    () => () => {
      clear();
    },
    [agentId, clear],
  );

  /** Replace only the same unchanged session after an explicit reload decision. */
  const reload = async () => {
    const state = useAgentBuilderDocumentStore.getState();
    if (state.dirty && !window.confirm(uiText("Reload 会放弃当前未保存修改，是否继续？"))) return;
    const result = await agentQuery.refetch();
    const current = useAgentBuilderDocumentStore.getState();
    if (current.sessionId !== state.sessionId) return;
    if (current.generation !== state.generation) {
      useToastStore.getState().pushToast({ message: uiText("重新加载期间有新编辑，未替换草稿。"), tone: "warning" });
      return;
    }
    // Query retains cached data on refetch failure; it is not a successful replacement.
    if (result.isError) {
      useToastStore.getState().pushToast({ message: uiText("重新加载失败，当前编辑已保留。"), tone: "error" });
      return;
    }
    if (result.data?.currentRevision) hydrate(result.data.currentRevision);
  };

  if (agentQuery.isLoading) return <div className={styles.emptyState}>{uiText("正在加载 Agent revision…")}</div>;
  if (agentQuery.error && !agentQuery.data) {
    return (
      <div className={styles.emptyState}>
        {uiText("无法加载 Agent：")}{agentQuery.error instanceof Error ? agentQuery.error.message : "unknown"}
      </div>
    );
  }
  if (!agentQuery.data?.currentRevision) {
    return <div className={styles.emptyState}>{uiText("Agent 没有 current revision。")}</div>;
  }
  if (legacyRevisionId) {
    return (
      <div className={styles.emptyState}>
        {uiText("此 Revision 使用历史 Studio 图契约，只能读取、导出和查看已有运行证据，不能继续编辑或发起新执行。 请从当前 Mobile Agent 能力模板显式创建一个新 Agent，再按 Inspector 中的实现与依赖重新配置；系统不会静默转换或替换该 Revision。")}</div>
    );
  }
  return (
    <AgentBuilderFlowProvider>
      <BuilderLeaveGuard />
      <BuilderLayout>
        <BuilderToolbar
          agentName={agentQuery.data.agent.name}
          catalogVersion={catalogQuery.data?.catalogVersion}
          onReload={reload}
        />
        <BuilderPalette
          catalog={catalogQuery.data ?? null}
          loading={catalogQuery.isLoading}
          error={
            catalogQuery.error instanceof Error ? catalogQuery.error.message : null
          }
        />
        <BuilderCanvas catalog={catalogQuery.data ?? null} />
        <BuilderInspector catalog={catalogQuery.data ?? null} />
      </BuilderLayout>
    </AgentBuilderFlowProvider>
  );
}
