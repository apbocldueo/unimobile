import { useCallback, useRef, useState } from "react";
import { Panel, useReactFlow } from "@xyflow/react";
import {
  applyFlowDocument,
  serializeFlowDocument,
  tryParseFlowDocument,
  validateFlowForExport,
  type FlowDocumentV1,
} from "@/modules/flow-graph/flowDocument";
import { AGENT_STUDIO_FLOW_PRESETS } from "../flowPresetDocuments";
import { useFlowStudioUi } from "../context/FlowStudioUiContext";
import { useToastStore } from "@/stores/toastStore";

const LS_FLOW_NAME = "zx-agent-studio-flow-name-v1";
const LS_FLOW_ID = "zx-agent-studio-flow-id-v1";

function safeFileName(name: string) {
  return name.replace(/[<>:"/\\|?*]/g, "_").slice(0, 80) || "flow";
}

export function FlowDocumentToolbar() {
  const { getNodes, getEdges, setNodes, setEdges, fitView } = useReactFlow();
  const { portsVisible, setPortsVisible } = useFlowStudioUi();
  const pushToast = useToastStore((s) => s.pushToast);
  const [flowName, setFlowName] = useState(() => {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(LS_FLOW_NAME) ?? "未命名流程" : "未命名流程";
    } catch {
      return "未命名流程";
    }
  });
  const [templateOpen, setTemplateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const persistName = useCallback((name: string) => {
    setFlowName(name);
    try {
      localStorage.setItem(LS_FLOW_NAME, name);
    } catch {
      /* */
    }
  }, []);

  const getStoredFlowId = useCallback(() => {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(LS_FLOW_ID) : null;
    } catch {
      return null;
    }
  }, []);

  const setStoredFlowId = useCallback((id: string) => {
    try {
      localStorage.setItem(LS_FLOW_ID, id);
    } catch {
      /* */
    }
  }, []);

  const onExportDownload = useCallback(() => {
    const nodes = getNodes();
    const edges = getEdges();
    const issues = validateFlowForExport(nodes, edges);
    if (issues.length) {
      pushToast({
        message: `导出前校验失败：${issues.slice(0, 3).map((i) => i.message).join("；")}${issues.length > 3 ? "…" : ""}`,
        tone: "warning",
        durationMs: 7000,
      });
      return;
    }
    const fid = getStoredFlowId() ?? undefined;
    const doc = serializeFlowDocument(flowName, fid, nodes, edges);
    setStoredFlowId(doc.flowId);
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeFileName(flowName)}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    pushToast({ message: "已导出 JSON 文件", tone: "success" });
  }, [flowName, getEdges, getNodes, getStoredFlowId, pushToast, setStoredFlowId]);

  const onExportCopy = useCallback(async () => {
    const nodes = getNodes();
    const edges = getEdges();
    const issues = validateFlowForExport(nodes, edges);
    if (issues.length) {
      pushToast({
        message: `复制前校验失败：${issues[0]?.message ?? "存在非法连线"}`,
        tone: "warning",
        durationMs: 6000,
      });
      return;
    }
    const fid = getStoredFlowId() ?? undefined;
    const doc = serializeFlowDocument(flowName, fid, nodes, edges);
    setStoredFlowId(doc.flowId);
    try {
      await navigator.clipboard.writeText(JSON.stringify(doc, null, 2));
      pushToast({ message: "已复制 JSON 到剪贴板", tone: "success" });
    } catch {
      pushToast({ message: "复制失败（浏览器权限）", tone: "error" });
    }
  }, [flowName, getEdges, getNodes, getStoredFlowId, pushToast, setStoredFlowId]);

  const onDeleteSelection = useCallback(() => {
    const nodes = getNodes().filter((n) => n.selected);
    const edges = getEdges().filter((e) => e.selected);
    if (!nodes.length && !edges.length) {
      pushToast({ message: "请先选中节点或连线", tone: "info", durationMs: 2800 });
      return;
    }
    const nodeIds = new Set(nodes.map((n) => n.id));
    setEdges((eds) => eds.filter((e) => !e.selected && !nodeIds.has(e.source) && !nodeIds.has(e.target)));
    setNodes((nds) => nds.filter((n) => !n.selected));
    pushToast({ message: "已删除选中项", tone: "success", durationMs: 2600 });
  }, [getEdges, getNodes, pushToast, setEdges, setNodes]);

  const applyDocument = useCallback(
    (doc: FlowDocumentV1) => {
      const res = applyFlowDocument(doc);
      setNodes(res.nodes);
      setEdges(res.edges);
      persistName(doc.flowName);
      setStoredFlowId(doc.flowId);
      setTemplateOpen(false);
      setImportOpen(false);
      requestAnimationFrame(() => fitView({ padding: 0.2 }));
      pushToast({ message: "已加载流程到画布", tone: "success" });
    },
    [fitView, persistName, pushToast, setEdges, setNodes, setStoredFlowId],
  );

  const onPickTemplate = useCallback(
    (build: () => FlowDocumentV1) => {
      applyDocument(build());
    },
    [applyDocument],
  );

  const onImportConfirm = useCallback(() => {
    const parsed = tryParseFlowDocument(importText);
    if (!parsed.ok) {
      pushToast({ message: parsed.error, tone: "error" });
      return;
    }
    applyDocument(parsed.doc);
    setImportText("");
  }, [applyDocument, importText, pushToast]);

  const onFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      e.target.value = "";
      if (!f) return;
      const reader = new FileReader();
      reader.onload = () => {
        const text = String(reader.result ?? "");
        const parsed = tryParseFlowDocument(text);
        if (!parsed.ok) {
          pushToast({ message: `导入失败：${parsed.error}`, tone: "error" });
          return;
        }
        applyDocument(parsed.doc);
      };
      reader.readAsText(f, "utf-8");
    },
    [applyDocument, pushToast],
  );

  return (
    <>
      <Panel position="top-right" className="flow-toolbar-panel">
        <div className="flow-toolbar-row">
          <label className="flow-toolbar-label">
            流程名称
            <input
              className="flow-toolbar-input"
              value={flowName}
              onChange={(e) => persistName(e.target.value)}
            />
          </label>
        </div>
        <div className="flow-toolbar-row flow-toolbar-actions">
          <button type="button" className="flow-toolbar-btn" onClick={onExportDownload}>
            导出 JSON
          </button>
          <button type="button" className="flow-toolbar-btn" onClick={() => void onExportCopy()}>
            复制 JSON
          </button>
          <button type="button" className="flow-toolbar-btn" onClick={() => setTemplateOpen(true)}>
            加载模板
          </button>
          <button type="button" className="flow-toolbar-btn" onClick={() => setImportOpen(true)}>
            导入 JSON
          </button>
          <button type="button" className="flow-toolbar-btn flow-toolbar-btn--danger" onClick={onDeleteSelection}>
            删除选中
          </button>
          <button
            type="button"
            className="flow-toolbar-btn"
            onClick={() => setPortsVisible(!portsVisible)}
            title="隐藏端口时将禁用新建连线"
          >
            {portsVisible ? "隐藏端口" : "显示端口"}
          </button>
        </div>
      </Panel>

      <input ref={fileRef} type="file" accept="application/json,.json" className="sr-only" onChange={onFile} />

      {templateOpen ? (
        <div className="flow-modal-backdrop" role="presentation" onMouseDown={() => setTemplateOpen(false)}>
          <div className="flow-modal" role="dialog" aria-labelledby="tpl-title" onMouseDown={(e) => e.stopPropagation()}>
            <div className="flow-modal-head">
              <h2 id="tpl-title" className="flow-modal-title">
                选择模板
              </h2>
              <button type="button" className="flow-modal-close" onClick={() => setTemplateOpen(false)} aria-label="关闭">
                ×
              </button>
            </div>
            <ul className="flow-modal-list">
              {AGENT_STUDIO_FLOW_PRESETS.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    className="flow-template-item"
                    onClick={() => onPickTemplate(t.build)}
                  >
                    <div className="flow-template-name">{t.name}</div>
                    <div className="flow-template-desc">{t.description}</div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {importOpen ? (
        <div className="flow-modal-backdrop" role="presentation" onMouseDown={() => setImportOpen(false)}>
          <div className="flow-modal flow-modal--wide" role="dialog" aria-labelledby="imp-title" onMouseDown={(e) => e.stopPropagation()}>
            <div className="flow-modal-head">
              <h2 id="imp-title" className="flow-modal-title">
                导入 JSON
              </h2>
              <button type="button" className="flow-modal-close" onClick={() => setImportOpen(false)} aria-label="关闭">
                ×
              </button>
            </div>
            <p className="flow-modal-hint">粘贴符合 Schema 的 JSON，或选择本地文件。</p>
            <textarea className="flow-modal-textarea" value={importText} onChange={(e) => setImportText(e.target.value)} rows={10} />
            <div className="flow-modal-actions">
              <button type="button" className="flow-toolbar-btn" onClick={() => fileRef.current?.click()}>
                选择文件
              </button>
              <button type="button" className="flow-toolbar-btn flow-toolbar-btn--primary" onClick={onImportConfirm}>
                应用
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
