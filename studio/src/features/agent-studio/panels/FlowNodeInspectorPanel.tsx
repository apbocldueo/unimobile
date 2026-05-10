import { useCallback, useMemo } from "react";
import { useNodes, useReactFlow } from "@xyflow/react";
import { useAgentStudioFlowStore } from "@/stores/agentStudioFlowStore";
import type { FlowPaletteNodeData } from "@/modules/flow-graph/flowNodeData";

function shortNodeId(id: string) {
  if (id.length <= 12) return id;
  return `${id.slice(0, 10)}…`;
}

/**
 * If-Else 节点检查器：核心组件配置已内嵌于画布节点，此处仅保留分支条件等专用编辑。
 */
export function FlowNodeInspectorPanel() {
  const { getNode, setNodes } = useReactFlow();
  const nodes = useNodes();
  const selectedNodeIds = useAgentStudioFlowStore((s) => s.selectedNodeIds);

  const selection = useMemo(() => {
    if (selectedNodeIds.length !== 1) return null;
    const n = getNode(selectedNodeIds[0]!);
    if (!n || n.type !== "ifElseFlow") return null;
    return { id: n.id, data: n.data as FlowPaletteNodeData };
  }, [getNode, selectedNodeIds, nodes]);

  const closeInspector = useCallback(() => {
    setNodes((nds) => nds.map((n) => ({ ...n, selected: false })));
    useAgentStudioFlowStore.getState().setSelectedNodeIds([]);
  }, [setNodes]);

  const patchNodeData = useCallback(
    (nodeId: string, patch: Partial<FlowPaletteNodeData>) => {
      setNodes((nds) =>
        nds.map((n) => {
          if (n.id !== nodeId) return n;
          return { ...n, data: { ...(n.data as FlowPaletteNodeData), ...patch } };
        }),
      );
    },
    [setNodes],
  );

  const onIfElseNoteChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      if (!selection) return;
      patchNodeData(selection.id, { condition_note: e.target.value });
    },
    [patchNodeData, selection],
  );

  if (!selection) return null;

  const rawDesc = selection.data.desc?.trim() ?? "";
  const descText = rawDesc || "—";
  const idShort = shortNodeId(selection.id);
  const metaLine = `分支控制 · ID: ${idShort}`;

  return (
    <div className="flow-node-inspector-shell" aria-label="If-Else 节点检查器">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 pr-1">
          <h2 className="flow-inspector-title">If-Else</h2>
          <p className="flow-inspector-meta mt-2">{metaLine}</p>
        </div>
        <button type="button" className="flow-inspector-close" aria-label="关闭检查器" onClick={closeInspector}>
          ×
        </button>
      </header>

      <hr className="flow-inspector-rule" aria-hidden />

      <div className="flex min-h-0 items-center gap-2 py-3">
        <p className="flow-inspector-desc min-w-0 flex-1" title={rawDesc || undefined}>
          {descText}
        </p>
        {rawDesc.length > 42 ? (
          <span className="flow-inspector-info" title={rawDesc} aria-label="完整说明">
            ?
          </span>
        ) : null}
      </div>

      <hr className="flow-inspector-rule" aria-hidden />

      <div className="flow-node-inspector-scroll flex min-h-0 flex-1 flex-col pt-3">
        <div className="flex flex-col gap-4">
          <div>
            <div className="flow-inspector-field-label">
              <label htmlFor="ifelse-condition-note">条件说明</label>
              <span className="flow-inspector-field-hint-icon" title="可填写分支判断备注，便于团队协作理解。">
                ?
              </span>
            </div>
            <textarea
              id="ifelse-condition-note"
              className="flow-inspector-textarea"
              placeholder="可填写备注，例如：是否启用 Verifier"
              value={selection.data.condition_note ?? ""}
              onChange={onIfElseNoteChange}
              onPointerDown={(e) => e.stopPropagation()}
            />
          </div>
          <div>
            <div className="flow-inspector-field-label">分支规则</div>
            <div className="flow-inspector-callout">
              选择「使用」走 <strong className="text-[#eeeeee]">True</strong> 分支（上侧输出）；「不使用」走{" "}
              <strong className="text-[#eeeeee]">False</strong> 分支（下侧输出）。与 Verifier / Perception 等业务连线一致即可。
            </div>
          </div>
          <p className="flow-inspector-help">
            当前算子：<span className="text-[#e8ecf4]">{selection.data.operator_value === "use" ? "使用" : "不使用"}</span>
            <span className="mx-1 opacity-50">·</span>
            可在节点卡片上直接切换 Operator
          </p>
        </div>
      </div>
    </div>
  );
}
