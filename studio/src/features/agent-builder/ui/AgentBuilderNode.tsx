import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { BuilderFlowNode } from "../model/flowAdapter";
import { handleId } from "../model/flowAdapter";
import { canvasSafeText } from "@/entities/agent-graph";
import styles from "./agentBuilder.module.css";

const KIND_ICONS: Record<string, string> = {
  capability: "◆",
  input: "↦",
  output: "↤",
  condition: "◇",
  router: "⑂",
  state: "▣",
  subgraph: "▤",
  loop: "↻",
};

/** Render one generic Catalog or control node without component-specific code. */
export function AgentBuilderNode({ id, data, selected }: NodeProps<BuilderFlowNode>) {
  const inputs = data.ports.filter((port) => port.direction === "input");
  const outputs = data.ports.filter((port) => port.direction === "output");
  const severityClass =
    data.diagnosticSeverity === "error"
      ? styles.nodeError
      : data.diagnosticSeverity === "warning"
        ? styles.nodeWarning
        : "";
  const compactClass =
    data.renderMode === "inline"
      ? styles.nodeInline
      : data.renderMode === "boundary"
        ? styles.nodeBoundary
        : "";
  const capabilityClass =
    data.capabilityKind === "core"
      ? styles.nodeCore
      : data.capabilityKind === "extension"
        ? styles.nodeExtension
        : styles.nodeRuntimeGlue;
  if (data.renderMode !== "card") {
    return (
      <article
        className={[
          styles.compactNode,
          compactClass,
          capabilityClass,
          selected ? styles.nodeSelected : "",
          data.unavailable ? styles.nodeUnavailable : "",
          severityClass,
        ].join(" ")}
        data-render-mode={data.renderMode}
        data-capability-kind={data.capabilityKind}
        data-testid={`builder-node-${id}`}
        aria-label={`${data.label} · ${data.renderMode === "inline" ? "运行步骤" : "画布边界"}`}
        title={data.description}
      >
        <span className={styles.compactIcon}>{KIND_ICONS[data.kind] ?? "◆"}</span>
        <strong className={styles.compactTitle}>{data.label}</strong>
        {data.diagnosticCount > 0 ? (
          <span className={styles.compactDiagnostic} aria-label={`${data.diagnosticCount} 条诊断`}>
            {data.diagnosticCount}
          </span>
        ) : null}
        {inputs.map((port, index) => (
          <Handle
            key={port.id}
            id={handleId(id, "input", port.id)}
            type="target"
            position={Position.Left}
            className={`${styles.handle} ${styles.compactHandle}`}
            style={{ top: `${((index + 1) / (inputs.length + 1)) * 100}%` }}
            title={`${canvasSafeText(port.id, "port")}: ${port.dataTypes.join(" | ")}`}
            aria-label={`输入连接 ${canvasSafeText(port.id, "port")}`}
          />
        ))}
        {outputs.map((port, index) => (
          <Handle
            key={port.id}
            id={handleId(id, "output", port.id)}
            type="source"
            position={Position.Right}
            className={`${styles.handle} ${styles.compactHandle}`}
            style={{ top: `${((index + 1) / (outputs.length + 1)) * 100}%` }}
            title={`${canvasSafeText(port.id, "port")}: ${port.dataTypes.join(" | ")}`}
            aria-label={`输出连接 ${canvasSafeText(port.id, "port")}`}
          />
        ))}
      </article>
    );
  }
  return (
    <article
      className={[
        styles.node,
        capabilityClass,
        selected ? styles.nodeSelected : "",
        data.unavailable ? styles.nodeUnavailable : "",
        severityClass,
      ].join(" ")}
      data-render-mode={data.renderMode}
      data-capability-kind={data.capabilityKind}
      data-testid={`builder-node-${id}`}
    >
      <header className={styles.nodeHeader}>
        <span className={styles.nodeIcon}>{KIND_ICONS[data.kind] ?? "◆"}</span>
        <span className={styles.nodeTitle}>{data.label}</span>
        <span className={styles.nodeKind}>
          {data.capabilityKind === "core" ? "core" : data.kind}
        </span>
      </header>
      <p className={styles.nodeDescription}>{data.description}</p>
      {data.unavailable ? <p className={styles.nodeUnavailableText}>Catalog unavailable</p> : null}
      <div className={styles.portRows}>
        <div className={styles.portColumn}>
          {inputs.map((port) => (
            <div key={port.id} className={styles.inputPortRow}>
              <Handle
                id={handleId(id, "input", port.id)}
                type="target"
                position={Position.Left}
                className={styles.handle}
              />
              <span title={port.dataTypes.join(" | ")}>
                {canvasSafeText(port.id, "port")}
                {port.required ? " *" : ""}
              </span>
            </div>
          ))}
        </div>
        <div className={styles.portColumn}>
          {outputs.map((port) => (
            <div key={port.id} className={styles.outputPortRow}>
              <span title={port.dataTypes.join(" | ")}>{canvasSafeText(port.id, "port")}</span>
              <Handle
                id={handleId(id, "output", port.id)}
                type="source"
                position={Position.Right}
                className={styles.handle}
              />
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}
