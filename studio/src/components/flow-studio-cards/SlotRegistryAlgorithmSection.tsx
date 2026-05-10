import { useCallback, useEffect, useMemo } from "react";
import { useNodeId, useReactFlow } from "@xyflow/react";
import type { FlowPaletteNodeData } from "@/modules/flow-graph/flowNodeData";
import { getSlotAlgorithmOptions } from "@/domain/agent/slotAlgorithmOptions";
import { getDefaultSlotParamValues } from "@/domain/agent/pluginParamUi";
import { AlgorithmQuickPicker } from "@/features/agent-studio/canvas/AlgorithmQuickPicker";
import { PluginParamForm } from "@/components/plugin-params/PluginParamForm";
import { useStudioAgentRegistryStore } from "@/stores/studioAgentRegistryStore";
import { useToastStore } from "@/stores/toastStore";
import { getStudioApiBase } from "@/services/studioRegistryClient";

const ALGO_FIELD_HINT = "仅展示本槽位在 ZhiXing 注册表中的插件；选择后将加载默认超参数，可在下方继续调整。";

export function SlotRegistryAlgorithmSection({ registrySlotId, data }: { registrySlotId: string; data: FlowPaletteNodeData }) {
  const nodeId = useNodeId();
  const { setNodes } = useReactFlow();
  const modular = useStudioAgentRegistryStore((s) => s.data?.modular);
  const pushToast = useToastStore((s) => s.pushToast);

  useEffect(() => {
    if (!getStudioApiBase()) return;
    const reg = useStudioAgentRegistryStore.getState();
    if (reg.status === "idle" || (reg.status === "error" && !reg.data)) void reg.refresh();
  }, []);

  const patchNodeData = useCallback(
    (patch: Partial<FlowPaletteNodeData>) => {
      const nid = nodeId;
      if (!nid) return;
      setNodes((nds) =>
        nds.map((n) => (n.id === nid && n.type === "studioPalette" ? { ...n, data: { ...(n.data as FlowPaletteNodeData), ...patch } } : n)),
      );
    },
    [nodeId, setNodes],
  );

  const algoOptions = useMemo(() => getSlotAlgorithmOptions(registrySlotId, modular), [registrySlotId, modular]);
  const pluginId = data.selectedPluginId ?? "";

  const mergedParams = useMemo(() => {
    if (!pluginId) return data.pluginParamValues ?? {};
    return { ...getDefaultSlotParamValues(pluginId), ...(data.pluginParamValues ?? {}) };
  }, [pluginId, data.pluginParamValues]);

  const onPickPlugin = useCallback(
    (id: string) => {
      const title = algoOptions.find((o) => o.id === id)?.title ?? id;
      patchNodeData({
        selectedPluginId: id,
        selectedPluginTitle: title,
        pluginParamValues: getDefaultSlotParamValues(id),
      });
      pushToast({ message: `已选择算法「${title}」`, tone: "success", durationMs: 3600 });
    },
    [algoOptions, patchNodeData, pushToast],
  );

  const onParamChange = useCallback(
    (paramId: string, value: string) => {
      const cur = { ...(data.pluginParamValues ?? {}) };
      patchNodeData({ pluginParamValues: { ...cur, [paramId]: value } });
    },
    [data.pluginParamValues, patchNodeData],
  );

  return (
    <div className="flow-palette-node-config nodrag" onPointerDown={(e) => e.stopPropagation()}>
      {algoOptions.length === 0 ? (
        <p className="flow-palette-node-registry-hint">
          未连接元数据服务或未拉取到该槽位插件。请运行 <code className="flow-inspector-code">python -m zhixing.studio</code> 并配置{" "}
          <code className="flow-inspector-code">VITE_STUDIO_API_BASE</code>。
        </p>
      ) : (
        <>
          <div className="flow-inspector-field-label">
            <span>算法 / 插件</span>
            <span className="flow-inspector-field-hint-icon" title={ALGO_FIELD_HINT}>
              ?
            </span>
          </div>
          <AlgorithmQuickPicker
            appearance="inspector"
            options={algoOptions}
            value={pluginId}
            onPick={onPickPlugin}
            placeholder="选择算法…"
            variant={pluginId ? "default" : "cta"}
          />
          {pluginId ? (
            <div className="flow-palette-node-params">
              <PluginParamForm appearance="inspector" pluginId={pluginId} values={mergedParams} onChange={onParamChange} />
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
