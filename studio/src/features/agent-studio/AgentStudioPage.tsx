import { AgentStudioCanvas } from "@/features/agent-studio/canvas/AgentStudioCanvas";
import { FlowPaletteSidebar } from "@/features/agent-studio/panels/FlowPaletteSidebar";
import "@/features/agent-studio/agent-studio.css";

/**
 * 流程编辑（`/builder`）：统一画布——拖拽组件、端口连线、节点检查器；
 * 模板含 ModularAgent 参考拓扑；算法与 pluginParamUi 与注册表一致。
 */
export function AgentStudioPage() {
  return (
    <div className="flow-agent-studio">
      <FlowPaletteSidebar />
      <AgentStudioCanvas />
    </div>
  );
}
