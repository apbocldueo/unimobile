import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type FlowStudioUiState = {
  portsVisible: boolean;
  setPortsVisible: (v: boolean) => void;
  /** `${nodeId}:${portId}` 用于连线选中时同步高亮端口 */
  highlightedHandleKeys: ReadonlySet<string>;
  setHighlightedHandleKeys: (s: ReadonlySet<string>) => void;
};

const FlowStudioUiContext = createContext<FlowStudioUiState | null>(null);

export function FlowStudioUiProvider({ children }: { children: ReactNode }) {
  const [portsVisible, setPortsVisible] = useState(true);
  const [highlightedHandleKeys, setHighlightedHandleKeys] = useState<ReadonlySet<string>>(() => new Set());

  const value = useMemo<FlowStudioUiState>(
    () => ({
      portsVisible,
      setPortsVisible,
      highlightedHandleKeys,
      setHighlightedHandleKeys,
    }),
    [portsVisible, highlightedHandleKeys],
  );

  return <FlowStudioUiContext.Provider value={value}>{children}</FlowStudioUiContext.Provider>;
}

export function useFlowStudioUi(): FlowStudioUiState {
  const v = useContext(FlowStudioUiContext);
  if (!v) throw new Error("useFlowStudioUi must be used within FlowStudioUiProvider");
  return v;
}

export function useHandleHighlightKey(nodeId: string | undefined, portId: string) {
  const { highlightedHandleKeys } = useFlowStudioUi();
  if (!nodeId) return false;
  return highlightedHandleKeys.has(`${nodeId}:${portId}`);
}
