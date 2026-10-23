import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { memo, type KeyboardEvent } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { BuilderFlowNode } from "../model/flowAdapter";
import { handleId } from "../model/flowAdapter";
import { canvasSafeText } from "@/entities/agent-graph";
import { portDataHint, portLabel, portRuntimeHint } from "../model/portPresentation";
import { capabilityPurpose } from "../model/builderPresentation";
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

/** Use the existing click-to-connect behavior for focused ports without moving a node.
 * Args: event is a keyboard event from the currently focused port.
 * Returns: Nothing; Enter/Space activate that port and consume the key.
 */
function connectFromKeyboard(event: KeyboardEvent<HTMLDivElement>): void {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  event.stopPropagation();
  event.currentTarget.click();
}

/** Render capability purpose, implementation summary and labeled connection handles.
 * Args: XYFlow props contain display data, selection, and stable handle identity.
 * Returns: A card or boundary with its existing typed connection handles.
 */
function BuilderNode({ id, data, selected }: NodeProps<BuilderFlowNode>) {
  useUiLocale();
  const expanded = data.kind !== "capability" || selected || data.connectionFocus || Boolean(data.relationEndpoint);
  const inputs = data.ports.filter((port) => port.direction === "input" &&
    (expanded || port.required || data.connectedPortIds?.includes(port.id)));
  const hiddenCount = data.ports.filter((port) => port.direction === "input").length - inputs.length;
  const defaultDescription = data.family ? capabilityPurpose[data.family] : data.description;
  const description = data.description === data.componentIdentifier || data.description === `${data.family} capability`
    ? defaultDescription
    : data.description;
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
  /** Style candidate handles using the same validator as connection commits. */
  const portClassName = (port: BuilderFlowNode["data"]["ports"][number], direction: "input" | "output") => {
    const currentHandleId = handleId(id, direction, port.id);
    const active = data.connectionHandleId === currentHandleId;
    const candidate = data.connectionCandidateHandles?.includes(currentHandleId) ?? false;
    const muted = Boolean(data.connectionFocus) && !active && !candidate;
    const relationFocused = data.relationPortId === port.id && Boolean(data.relationEndpoint);
    return [
      styles.handle,
      active ? styles.handleActive : "",
      candidate ? styles.handleCandidate : "",
      muted ? styles.handleMuted : "",
      relationFocused ? styles.handleRelationFocus : "",
    ].join(" ");
  };
  if (data.renderMode !== "card") {
    return (
      <article
        className={[
          styles.compactNode,
          compactClass,
          capabilityClass,
          selected ? styles.nodeSelected : "",
          data.unavailable ? styles.nodeUnavailable : "",
          data.relationEndpoint === "source" ? styles.nodeRelationSource : "",
          data.relationEndpoint === "target" ? styles.nodeRelationTarget : "",
          severityClass,
        ].join(" ")}
        data-render-mode={data.renderMode}
        data-capability-kind={data.capabilityKind}
        data-testid={`builder-node-${id}`}
        aria-label={`${data.label} · ${data.renderMode === "inline" ? uiText("运行步骤") : uiText("画布边界")}`}
        title={data.description}
      >
        <span className={styles.compactIcon}>{KIND_ICONS[data.kind] ?? "◆"}</span>
        <strong className={styles.compactTitle}>{data.label}</strong>
        {data.relationEndpoint ? <small className={styles.relationEndpointBadge}>{data.relationEndpoint === "source" ? uiText("连线起点") : uiText("连线终点")}</small> : null}
        {data.connectionCandidateHandles?.some((handle) => handle.startsWith(`${id}:`)) ? (
          <small className={styles.portCandidateBadge}>{uiText("可连接")}</small>
        ) : null}
        {data.diagnosticCount > 0 ? (
          <span className={styles.compactDiagnostic} aria-label={uiMessage`${data.diagnosticCount} 条诊断`}>
            {data.diagnosticCount}
          </span>
        ) : null}
        {inputs.map((port, index) => (
          <Handle
                role="button" tabIndex={0} onKeyDown={connectFromKeyboard}
            key={port.id}
            id={handleId(id, "input", port.id)}
            type="target"
            position={Position.Left}
            className={`${portClassName(port, "input")} ${styles.compactHandle}`}
            style={{ top: `${((index + 1) / (inputs.length + 1)) * 100}%` }}
            title={portRuntimeHint(port, data.family) ?? portDataHint(port)}
            aria-label={uiMessage`输入连接 ${portLabel(port.id)}`}
          />
        ))}
        {outputs.map((port, index) => (
          <Handle
                role="button" tabIndex={0} onKeyDown={connectFromKeyboard}
            key={port.id}
            id={handleId(id, "output", port.id)}
            type="source"
            position={Position.Right}
            className={`${portClassName(port, "output")} ${styles.compactHandle}`}
            style={{ top: `${((index + 1) / (outputs.length + 1)) * 100}%` }}
            title={portRuntimeHint(port, data.family) ?? portDataHint(port)}
            aria-label={uiMessage`输出连接 ${portLabel(port.id)}`}
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
        data.relationEndpoint === "source" ? styles.nodeRelationSource : "",
        data.relationEndpoint === "target" ? styles.nodeRelationTarget : "",
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
        {data.relationEndpoint ? <small className={styles.relationEndpointBadge}>{data.relationEndpoint === "source" ? uiText("连线起点") : uiText("连线终点")}</small> : null}
      </header>
      {description ? <p className={styles.nodeDescription}>{description}</p> : null}
      {data.kind === "capability" ? <div className={styles.nodeSummary}>
        <span className={styles.nodeSummaryLabel}>{uiText("实现")}</span>
        <strong>{data.implementationLabel ?? uiText("未找到实现")}</strong>
        {(data.implementationCount ?? 0) > 1 ? <small>{uiText("共")}{" "}{data.implementationCount} {" "}{uiText("个候选实现")}</small> : null}
      </div> : null}
      {data.unavailable || data.diagnosticCount > 0 ? <p className={styles.nodeIssue} data-severity={data.unavailable ? "error" : data.diagnosticSeverity}>
        {data.unavailable ? uiText("实现不可用 · 请选择其他实现") : uiMessage`${data.diagnosticCount} 项${data.diagnosticSeverity === "error" ? uiText("问题待修复") : uiText("检查提示")} · 查看检查面板`}
      </p> : null}
      <div className={styles.portRows}>
        <div className={styles.portColumn}>
          <span className={styles.portHeading}>{uiText("接收")}</span>
          {inputs.map((port) => (
            <div key={port.id} className={`${styles.inputPortRow} ${data.connectionFocus && !data.connectionCandidateHandles?.includes(handleId(id, "input", port.id)) && data.connectionHandleId !== handleId(id, "input", port.id) ? styles.portRowMuted : ""}`}>
              <Handle
                role="button" tabIndex={0} onKeyDown={connectFromKeyboard}
                id={handleId(id, "input", port.id)}
                type="target"
                position={Position.Left}
                className={portClassName(port, "input")}
                title={portRuntimeHint(port, data.family) ?? portDataHint(port)}
                aria-label={uiMessage`输入连接 ${portLabel(port.id)}`}
              />
              <span title={portRuntimeHint(port, data.family) ?? portDataHint(port)}>
                {portLabel(canvasSafeText(port.id, "port"))}
                {port.required ? " *" : ""}
                {data.relationEndpoint && data.relationPortId === port.id ? <small className={styles.relationPortBadge}>{data.relationEndpoint === "source" ? uiText("起点") : uiText("终点")}</small> : null}
                {data.connectionCandidateHandles?.includes(handleId(id, "input", port.id)) ? <small className={styles.portCandidateBadge}>{uiText("可连接")}</small> : null}
              </span>
            </div>
          ))}
        </div>
        <div className={styles.portColumn}>
          <span className={styles.portHeading}>{uiText("输出")}</span>
          {outputs.map((port) => (
            <div key={port.id} className={`${styles.outputPortRow} ${data.connectionFocus && !data.connectionCandidateHandles?.includes(handleId(id, "output", port.id)) && data.connectionHandleId !== handleId(id, "output", port.id) ? styles.portRowMuted : ""}`}>
              <span title={portRuntimeHint(port, data.family) ?? portDataHint(port)}>{portLabel(canvasSafeText(port.id, "port"))}{data.relationEndpoint && data.relationPortId === port.id ? <small className={styles.relationPortBadge}>{data.relationEndpoint === "source" ? uiText("起点") : uiText("终点")}</small> : null}{data.connectionCandidateHandles?.includes(handleId(id, "output", port.id)) ? <small className={styles.portCandidateBadge}>{uiText("可连接")}</small> : null}</span>
              <Handle
                role="button" tabIndex={0} onKeyDown={connectFromKeyboard}
                id={handleId(id, "output", port.id)}
                type="source"
                position={Position.Right}
                className={portClassName(port, "output")}
                title={portRuntimeHint(port, data.family) ?? portDataHint(port)}
                aria-label={uiMessage`输出连接 ${portLabel(port.id)}`}
              />
            </div>
          ))}
        </div>
      </div>
      {hiddenCount > 0 ? <p className={styles.portDisclosure}>{uiText("选中展开")}{" "}{hiddenCount} {" "}{uiText("个可选输入")}</p> : null}
    </article>
  );
}

/** Keep stationary card content stable during geometry-only drag updates. */
export const AgentBuilderNode = memo(BuilderNode);
