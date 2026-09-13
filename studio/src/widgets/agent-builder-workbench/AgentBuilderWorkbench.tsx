import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchComponentCatalog } from "@/entities/component-catalog";
import { getStudioAgent } from "@/entities/agent";
import {
  BuilderCanvas,
  AgentBuilderFlowProvider,
  BuilderInspector,
  BuilderPalette,
  BuilderToolbar,
  agentBuilderStyles as styles,
  useAgentBuilderDocumentStore,
} from "@/features/agent-builder";

type AgentBuilderWorkbenchProps = {
  agentId: string;
};

/** Compose remote resources and the local Builder draft into the Stage 1 workbench. */
export function AgentBuilderWorkbench({ agentId }: AgentBuilderWorkbenchProps) {
  const hydrate = useAgentBuilderDocumentStore((state) => state.hydrate);
  const clear = useAgentBuilderDocumentStore((state) => state.clear);
  const dirty = useAgentBuilderDocumentStore((state) => state.dirty);
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
    [clear],
  );

  const reload = async () => {
    if (dirty && !window.confirm("Reload 会放弃当前未保存修改，是否继续？")) return;
    const result = await agentQuery.refetch();
    if (result.data?.currentRevision) hydrate(result.data.currentRevision);
  };

  if (agentQuery.isLoading) return <div className={styles.emptyState}>正在加载 Agent revision…</div>;
  if (agentQuery.error) {
    return (
      <div className={styles.emptyState}>
        无法加载 Agent：{agentQuery.error instanceof Error ? agentQuery.error.message : "unknown"}
      </div>
    );
  }
  if (!agentQuery.data?.currentRevision) {
    return <div className={styles.emptyState}>Agent 没有 current revision。</div>;
  }
  if (legacyRevisionId) {
    return (
      <div className={styles.emptyState}>
        此 Revision 使用历史 Studio 图契约，只能读取、导出和查看已有运行证据，不能继续编辑或发起新执行。
        请从当前 Mobile Agent 能力模板显式创建一个新 Agent，再按 Inspector 中的实现与依赖重新配置；系统不会静默转换或替换该 Revision。
      </div>
    );
  }
  return (
    <AgentBuilderFlowProvider>
      <div className={styles.workbench}>
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
      </div>
    </AgentBuilderFlowProvider>
  );
}
