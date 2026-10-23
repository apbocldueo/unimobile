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
  const registryStatus = useStudioAgentRegistryStore((s) => s.status);
  const registryError = useStudioAgentRegistryStore((s) => s.error);
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
  const studioBase = getStudioApiBase();
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
          {!studioBase ? (
            <>
              前端未配置 Studio 元数据地址（预览/生产构建下 <code className="flow-inspector-code">import.meta.env.DEV</code> 为 false）。请先运行{" "}
              <code className="flow-inspector-code">python -m zhixing.studio</code>，再在构建或预览环境中设置环境变量{" "}
              <code className="flow-inspector-code">VITE_STUDIO_API_BASE=http://127.0.0.1:8765</code>（不要带 <code className="flow-inspector-code">/zhixing-studio</code>
              后缀）。开发模式 <code className="flow-inspector-code">npm run dev</code> 可不设，默认走 Vite 代理。
            </>
          ) : registryStatus === "idle" ? (
            <>正在连接元数据服务…</>
          ) : registryStatus === "loading" ? (
            <>正在加载插件注册表…</>
          ) : registryStatus === "error" ? (
            <>拉取注册表失败：{registryError ?? "未知错误"}。请确认 <code className="flow-inspector-code">python -m zhixing.studio</code> 在运行且端口与{" "}
            <code className="flow-inspector-code">VITE_STUDIO_API_BASE</code> / Vite 代理一致。</>
          ) : (
            <>
              槽位「{registrySlotId}」在注册表中没有条目（<code className="flow-inspector-code">pluginsBySlot.{registrySlotId}</code> 为空）。兵工厂只展示{" "}
              <code className="flow-inspector-code">
                {`@PluginRegistry.register(namespace="agent.${registrySlotId}", name="…")`}
              </code>{" "}
              的类，且需能被 <code className="flow-inspector-code">import zhixing.plugins…</code> 加载（与 <code className="flow-inspector-code">run.py</code> 的 autodiscover 一致）；<code className="flow-inspector-code">plugins/benchmark</code>、
              <code className="flow-inspector-code">plugins/llm</code> 不在 Modular 槽位。请查 <code className="flow-inspector-code">temp/log/zhixing_studio.log</code>：启动时应有一行{" "}
              <code className="flow-inspector-code">agent-registry warm-up OK, pluginsBySlot counts</code>；若某槽位为 0，再搜 <code className="flow-inspector-code">Plugin Import Error</code>（模块顶层 import 失败会导致该文件未注册）。
            </>
          )}
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
