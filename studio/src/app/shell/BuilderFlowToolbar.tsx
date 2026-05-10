import { useLocation } from "react-router-dom";
import { useAgentBuilderStore } from "@/stores/agentBuilderStore";
import { STUDIO_BUILDER_FLOATING_SURFACE_CLASS } from "./studioBuilderChrome";
import { useBuilderFlowToolbarActions } from "@/features/agent-studio/toolbar/useBuilderFlowToolbarActions";

/**
 * 兵工厂流程画布：底部浮动操作栏。
 * 布局与样式变量见 `globals.css`（`--studio-builder-toolbar-*`）；业务逻辑见 `agent-studio/toolbar/useBuilderFlowToolbarActions`。
 * 扩展：在对应 `role="group"` 内追加按钮，顺序保持 辅助 → 次要 → 主（第五章）。
 */
export function BuilderFlowToolbar() {
  const location = useLocation();
  const onBuilder = location.pathname.startsWith("/builder");
  const flowWorkbenchPhase = useAgentBuilderStore((s) => s.flowWorkbenchPhase);
  const { flowReady, savePending, resetPending, runPending, onSave, onRun, onReset } = useBuilderFlowToolbarActions();

  const onBuilderEditor = onBuilder && flowWorkbenchPhase === "flow_editor";

  if (!onBuilderEditor) return null;

  return (
    <div
      className="pointer-events-none absolute bottom-4 left-4 right-0 z-[30] flex justify-end"
      role="toolbar"
      aria-label="流程操作"
    >
      <div
        className={`pointer-events-auto ${STUDIO_BUILDER_FLOATING_SURFACE_CLASS} studio-builder-toolbar__shell`}
      >
        <div className="studio-builder-toolbar__group" role="group" aria-label="辅助操作">
          {/* 扩展位：导出配置、复制流程等 */}
          <button
            type="button"
            disabled={resetPending}
            className="studio-builder-toolbar-btn studio-builder-toolbar-btn--aux"
            onClick={() => void onReset()}
          >
            重置
          </button>
        </div>
        <div className="studio-builder-toolbar__group" role="group" aria-label="次要操作">
          <button
            type="button"
            disabled={savePending}
            className="studio-builder-toolbar-btn studio-builder-toolbar-btn--secondary"
            onClick={() => void onSave()}
          >
            保存
          </button>
        </div>
        <div className="studio-builder-toolbar__group" role="group" aria-label="主操作">
          <button
            type="button"
            disabled={!flowReady || runPending}
            title={flowReady ? undefined : "完成全部组件配置后即可运行"}
            className="studio-builder-toolbar-btn studio-builder-toolbar-btn--primary"
            onClick={() => void onRun()}
          >
            运行
          </button>
        </div>
      </div>
    </div>
  );
}
