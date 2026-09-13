import { ReactFlowProvider } from "@xyflow/react";
import type { ReactNode } from "react";

/** Keep XYFlow instance state inside the Builder feature boundary. */
export function AgentBuilderFlowProvider({ children }: { children: ReactNode }) {
  return <ReactFlowProvider>{children}</ReactFlowProvider>;
}
