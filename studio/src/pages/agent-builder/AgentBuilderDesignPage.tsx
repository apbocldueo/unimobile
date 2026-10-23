import { Navigate, useParams } from "react-router-dom";
import { AgentBuilderWorkbench } from "@/widgets/agent-builder-workbench";
import { AgentWorkspaceFrame } from "@/widgets/agent-workspace";

/** Bind the stable URL resource identity to the Agent Builder workbench. */
export function AgentBuilderDesignPage() {
  const { agentId } = useParams<{ agentId: string }>();
  if (!agentId) return <Navigate to="/agents" replace />;
  return <AgentWorkspaceFrame agentId={agentId} activeMode="design"><AgentBuilderWorkbench agentId={agentId} /></AgentWorkspaceFrame>;
}
