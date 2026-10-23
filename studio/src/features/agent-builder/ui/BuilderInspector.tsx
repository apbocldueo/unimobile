import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { useEffect, useMemo } from "react";
import type { ComponentCatalog, ComponentCatalogItem } from "@/entities/component-catalog";
import type { JsonValue } from "@/shared/lib";
import type {
  StudioCapabilityNode,
  StudioCapabilityRelation,
  StudioFlowDocument,
} from "@/entities/agent-graph";
import { candidateIdentity, rawFieldKey } from "../model/editSession";
import { capabilityPurpose } from "../model/builderPresentation";
import { BuilderJsonField as JsonField } from "./BuilderJsonField";
import { ComponentConfigForm } from "./ComponentConfigForm";
import { LlmDependencyForm } from "./LlmDependencyForm";
import { componentForNode } from "../model/flowAdapter";
import { portsForNode } from "../model/flowAdapter";
import { portLabel } from "../model/portPresentation";
import { relationKindLabel } from "../model/relationPresentation";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { diagnosticAdvice, diagnosticTarget } from "../model/diagnosticGuidance";
import { useCanvasInteractionStore } from "../model/canvasInteraction.store";
import { configDefaults } from "../model/configDefaults";
import styles from "./agentBuilder.module.css";

import { useBuilderPanels } from "./BuilderPanelContext";

type BuilderInspectorProps = { catalog: ComponentCatalog | null };

/** Resolve available implementations from the authoritative family classification. */
function implementations(
  catalog: ComponentCatalog | null,
  node: StudioCapabilityNode,
): ComponentCatalogItem[] {
  return (catalog?.components ?? []).filter(
    (item) =>
      item.placement === "agent_capability" &&
      item.capabilityFamily === node.family &&
      item.availability.available,
  );
}

/** Replace an explicitly chosen candidate after the caller's discard guard. */
function replaceCandidate(
  node: StudioCapabilityNode,
  index: number,
  component: ComponentCatalogItem,
): StudioCapabilityNode {
  const candidates = [...node.implementation.candidates];
  candidates[index] = {
    namespace: component.namespace,
    name: component.name,
    version: component.version,
    params: configDefaults(component.configSchema),
    dependencies: {},
  };
  return { ...node, implementation: { ...node.implementation, candidates } };
}

/** Present a capability's implementation and session-owned configuration fields. */
function CapabilityInspector({
  node,
  catalog,
  onUpdate,
  onCandidatePropertyChange,
  onDelete,
}: {
  node: StudioCapabilityNode;
  catalog: ComponentCatalog | null;
  onUpdate: (node: StudioCapabilityNode) => void;
  onCandidatePropertyChange: (candidateIndex: number, value: Record<string, JsonValue>, property?: "params" | "dependencies") => void;
  onDelete: () => void;
}) {
  const uiLocale = useUiLocale();
  const choices = implementations(catalog, node);
  const selected = componentForNode(node, catalog);
  const first = node.implementation.candidates[0]!;
  const rawFields = useAgentBuilderDocumentStore((state) => state.rawFields);
  const rawParams = rawFields[rawFieldKey({
    canvasId: node.canvasId,
    candidate: 0,
    implementation: candidateIdentity(node, 0),
    property: "params",
  })];
  const rawDependencies = rawFields[rawFieldKey({
    canvasId: node.canvasId,
    candidate: 0,
    implementation: candidateIdentity(node, 0),
    property: "dependencies",
  })];
  const formParams = useMemo(() => {
    if (!rawParams || rawParams.error) return first.params;
    try {
      const parsed = JSON.parse(rawParams.text) as unknown;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed as Record<string, JsonValue>
        : first.params;
    } catch {
      return first.params;
    }
  }, [first.params, rawParams, uiLocale]);
  const formDependencies = useMemo(() => {
    if (!rawDependencies || rawDependencies.error) return first.dependencies;
    try {
      const parsed = JSON.parse(rawDependencies.text) as unknown;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed as Record<string, JsonValue>
        : first.dependencies;
    } catch {
      return first.dependencies;
    }
  }, [first.dependencies, rawDependencies, uiLocale]);
  /** Require an explicit discard before replacing a raw-field owner. */
  const replaceImplementation = (next: StudioCapabilityNode) => {
    if (useAgentBuilderDocumentStore.getState().confirmDiscardFields([node.canvasId])) onUpdate(next);
  };
  return (
    <>
      <section className={styles.inspectorSection}>
        <h3 className={styles.capabilityTitle}>{catalog?.capabilityFamilies?.find((item) => item.family === node.family)?.label ?? node.family}</h3>
        <p className={styles.purpose}>{capabilityPurpose[node.family]}</p>
      </section>
      <section className={styles.inspectorSection}>
        <h3 className={styles.sectionTitle}>{uiText("实现方式")}</h3>
        <div className={styles.field}>
          <label>{uiText("组件与版本")}</label>
          <select
            aria-label="Exact implementation / version"
            className={styles.select}
            value={selected?.identifier ?? ""}
            onChange={(event) => {
              const component = choices.find((item) => item.identifier === event.target.value);
              if (component) replaceImplementation(replaceCandidate(node, 0, component));
            }}
          >
            {!selected ? <option value="">Unavailable selection</option> : null}
            {choices.map((item) => <option key={item.identifier} value={item.identifier}>{item.display.label} · {item.version}</option>)}
          </select>
        </div>
        {node.implementation.policy === "fallback" ? <p className={styles.callout}>Ordered fallback · {node.implementation.candidates.map((item) => `${item.name} · ${item.version}`).join(" → ")}</p> : null}
        {node.implementation.candidates.map((candidate, index) => (
          <div key={`${candidate.namespace}:${candidate.name}:${index}`} className={styles.repairCard}>
            <strong>{index === 0 ? uiText("首选") : uiMessage`备选 ${index}`} · {catalog?.components.find((item) => item.identifier === `${candidate.namespace}:${candidate.name}@${candidate.version}`)?.display.label ?? candidate.name} · {candidate.version}</strong>
            {index > 0 ? (
              <select
                aria-label={`Fallback ${index} implementation`}
                className={styles.select}
                value={`${candidate.namespace}:${candidate.name}@${candidate.version}`}
                onChange={(event) => {
                  const component = choices.find((item) => item.identifier === event.target.value);
                  if (component) replaceImplementation(replaceCandidate(node, index, component));
                }}
              >
                {choices.map((item) => <option key={item.identifier} value={item.identifier}>{item.display.label} · {item.version}</option>)}
              </select>
            ) : null}
            {index === 0 ? (
              <>
                <p className={styles.formHint}>{uiText("常用参数")}</p>
                <ComponentConfigForm
                  schema={selected?.configSchema ?? {}}
                  value={formParams}
                  onChange={(value) => onCandidatePropertyChange(index, value)}
                />
                <p className={styles.formHint}>
                  {uiText("依赖项：")}{(selected?.dependencySlots ?? []).map((slot) => `${slot.name} · ${candidate.dependencies[slot.name] ? uiText("已配置") : uiText("未配置")}`).join("；") || uiText("无额外依赖")}
                </p>
                {(selected?.dependencySlots ?? []).filter((slot) => slot.name === "llm").map((slot) => (
                  <LlmDependencyForm
                    key={slot.name}
                    slot={slot}
                    catalog={catalog}
                    value={formDependencies[slot.name]}
                    onChange={(value) => onCandidatePropertyChange(index, { ...formDependencies, [slot.name]: value }, "dependencies")}
                  />
                ))}
              </>
            ) : null}
            <details className={styles.advancedSettings} open={index === 0 && Boolean(rawParams?.error)}>
              <summary>{uiText("高级参数 JSON")}</summary>
            <JsonField
              key={`params:${candidateIdentity(node, index)}`}
              label={`Candidate ${index + 1} config`}
              value={candidate.params}
              owner={{ canvasId: node.canvasId, candidate: index, implementation: candidateIdentity(node, index), property: "params" }}
            />
            </details>
            {(catalog?.components.find((item) => item.identifier === `${candidate.namespace}:${candidate.name}@${candidate.version}`)?.dependencySlots ?? []).filter((slot) => slot.required && !candidate.dependencies[slot.name]).map((slot) => (
              <p key={slot.name} role="status" className={styles.callout}>{uiText("缺少必需依赖：")}{slot.name}{uiText("。请在下方 Dependencies 配置中补齐，并重新检查流程。凭证仅填写 SecretRef 引用。")}{" "}<a href="/help?topic=validation" target="_blank" rel="noopener noreferrer">{uiText("配置帮助 ↗")}</a></p>
            ))}
            <details className={styles.advancedSettings}>
              <summary>{uiText("高级依赖 JSON")}</summary>
              <JsonField
                key={`dependencies:${candidateIdentity(node, index)}`}
                label={`Candidate ${index + 1} dependencies`}
                value={candidate.dependencies}
                owner={{ canvasId: node.canvasId, candidate: index, implementation: candidateIdentity(node, index), property: "dependencies" }}
              />
            </details>
          </div>
        ))}
      </section>
        <details className={styles.advancedSettings}>
        <summary>{uiText("执行策略 ·")}{" "}{node.implementation.policy === "single" ? uiText("单一实现") : uiMessage`依次尝试 (${node.implementation.candidates.length})`}</summary>
        <div className={styles.field}>
          <label>Binding policy</label>
          <select
            aria-label="Binding policy"
            className={styles.select}
            value={node.implementation.policy}
            onChange={(event) => {
              const policy = event.target.value as "single" | "fallback";
              if (policy === "single") {
                replaceImplementation({ ...node, implementation: { policy, candidates: [first] } });
                return;
              }
              const fallback = choices.find((item) => item.identifier !== selected?.identifier) ?? selected;
              if (!fallback) return;
              replaceImplementation({
                ...node,
                implementation: {
                  policy,
                  candidates: [first, {
                    namespace: fallback.namespace,
                    name: fallback.name,
                    version: fallback.version,
                    params: {},
                    dependencies: {},
                  }],
                },
              });
            }}
          >
            <option value="single">single</option>
            <option value="fallback" disabled={choices.length < 2}>ordered fallback</option>
          </select>
        </div>
        </details>
      <details className={styles.technicalDetails}>
        <summary>{uiText("技术标识")}</summary>
        <dl className={styles.definitionList}>
          <div><dt>Family</dt><dd>{node.family}</dd></div>
          <div><dt>Logical ID</dt><dd>{node.logicalId}</dd></div>
          {node.implementation.candidates.map((candidate, index) => <div key={index}><dt>{index === 0 ? uiText("首选") : uiMessage`备选 ${index}`}</dt><dd>{candidate.namespace}:{candidate.name}@{candidate.version}</dd></div>)}
        </dl>
      </details>
      <button type="button" className={`${styles.button} ${styles.buttonDanger}`} onClick={onDelete}>
        {uiText("删除能力实例")}</button>
    </>
  );
}

/** Resolve a readable owner and port label for the relation inspector.
 * Args: document/catalog resolve authoring and Catalog identities; ownerId/portId identify one relation endpoint; target marks termination semantics.
 * Returns: A stable display label for the endpoint, with technical IDs retained separately below.
 */
function relationEndpointLabel(
  document: StudioFlowDocument,
  catalog: ComponentCatalog | null,
  ownerId: string,
  portId: string,
  target: boolean,
  relationKind: StudioCapabilityRelation["kind"],
): string {
  const object = [document.input, ...document.capabilities, document.output].find((item) => item.logicalId === ownerId);
  if (!object) return `${ownerId} · ${portLabel(portId)}`;
  const ownerLabel = "kind" in object
    ? object.kind === "input" ? "Input" : "Output"
    : document.presentation.nodes[object.canvasId]?.label || catalog?.capabilityFamilies?.find((item) => item.family === object.family)?.label || object.family;
  if (target && relationKind === "termination") return uiMessage`${ownerLabel} · 结束`;
  const ports = "family" in object ? portsForNode(object, catalog) : [];
  const port = ports.find((item) => item.id === portId);
  return `${ownerLabel} · ${portLabel(port?.id ?? portId)}`;
}

/** Edit the selected relation without introducing new connection semantics. */
function RelationInspector({
  relation,
  document,
  catalog,
  onUpdate,
  onDelete,
}: {
  relation: StudioCapabilityRelation;
  document: StudioFlowDocument;
  catalog: ComponentCatalog | null;
  onUpdate: (relation: StudioCapabilityRelation) => void;
  onDelete: () => void;
}) {
  useUiLocale();
  const sourceLabel = relationEndpointLabel(document, catalog, relation.source.ownerId, relation.source.portId, false, relation.kind);
  const targetLabel = relationEndpointLabel(document, catalog, relation.target.ownerId, relation.target.portId, true, relation.kind);
  return (
    <>
      <section className={styles.inspectorSection}>
        <h3 className={styles.sectionTitle}>{relationKindLabel(relation.kind)}</h3>
        <div className={styles.relationRouteSummary} aria-label={uiText("连线两端")}>
          <div className={`${styles.relationEndpointCard} ${styles.relationSourceCard}`}>
            <small>{uiText("来源")}</small>
            <strong>{sourceLabel}</strong>
          </div>
          <span className={styles.relationRouteArrow} aria-hidden>→</span>
          <div className={`${styles.relationEndpointCard} ${styles.relationTargetCard}`}>
            <small>{uiText("目标")}</small>
            <strong>{targetLabel}</strong>
          </div>
        </div>
        <dl className={styles.definitionList}>
          <div><dt>{uiText("关系类型")}</dt><dd>{relation.kind}</dd></div>
          <div><dt>{uiText("来源标识")}</dt><dd>{relation.source.ownerId}.{relation.source.portId}</dd></div>
          <div><dt>{uiText("目标标识")}</dt><dd>{relation.target.ownerId}.{relation.target.portId}</dd></div>
        </dl>
        {relation.kind === "feedback" && relation.feedback ? (
          <>
            <p className={styles.muted}>{uiText("来源结果满足条件时，回到目标节点开始下一轮。这里只编辑策略，运行时仍会由后端再次校验。")}</p>
            <div className={styles.field}>
              <label>{uiText("条件字段")}</label>
              <input
                aria-label="Feedback predicate field"
                className={styles.input}
                value={relation.feedback.predicate.field}
                onChange={(event) => onUpdate({
                  ...relation,
                  feedback: {
                    ...relation.feedback!,
                    predicate: { ...relation.feedback!.predicate, field: event.target.value },
                  },
                })}
              />
            </div>
            <div className={styles.field}>
              <label>{uiText("条件判断")}</label>
              <select
                aria-label="Feedback predicate operator"
                className={styles.select}
                value={relation.feedback.predicate.operator}
                onChange={(event) => {
                  const operator = event.target.value;
                  const predicate = { ...relation.feedback!.predicate, operator };
                  if (["truthy", "falsy", "exists"].includes(operator)) delete predicate.value;
                  onUpdate({ ...relation, feedback: { ...relation.feedback!, predicate } });
                }}
              >
                {(["truthy", "falsy", "exists", "eq", "ne", "gt", "gte", "lt", "lte"] as const).map((operator) => (
                  <option key={operator} value={operator}>{operator}</option>
                ))}
              </select>
            </div>
            {["truthy", "falsy", "exists"].includes(relation.feedback.predicate.operator) ? null : (
              <div className={styles.field}>
                <label>{uiText("条件值（JSON）")}</label>
                <input
                  aria-label="Feedback predicate value"
                  className={styles.input}
                  value={typeof relation.feedback.predicate.value === "string"
                    ? relation.feedback.predicate.value
                    : JSON.stringify(relation.feedback.predicate.value ?? "")}
                  onChange={(event) => {
                    try {
                      const value = JSON.parse(event.target.value) as JsonValue;
                      onUpdate({
                        ...relation,
                        feedback: { ...relation.feedback!, predicate: { ...relation.feedback!.predicate, value } },
                      });
                    } catch {
                      // Keep malformed JSON local to the input until the user completes it.
                    }
                  }}
                />
              </div>
            )}
            <div className={styles.field}>
              <label>{uiText("达到上限后")}</label>
              <select
                aria-label="Feedback exhausted policy"
                className={styles.select}
                value={relation.feedback.onExhausted}
                onChange={(event) => onUpdate({
                  ...relation,
                  feedback: { ...relation.feedback!, onExhausted: event.target.value as "fail" | "continue" | "terminate" },
                })}
              >
                <option value="fail">{uiText("fail（标记失败）")}</option>
                <option value="continue">{uiText("continue（继续后续流程）")}</option>
                <option value="terminate">{uiText("terminate（结束 Agent）")}</option>
              </select>
            </div>
            <div className={styles.field}>
              <label>{uiText("最多反馈轮数")}</label>
              <input
                aria-label="Maximum feedback iterations"
                className={styles.input}
                type="number"
                min={1}
                max={10}
                value={relation.feedback.maxIterations}
                onChange={(event) => onUpdate({
                  ...relation,
                  feedback: { ...relation.feedback!, maxIterations: Math.max(1, Math.min(10, Number(event.target.value))) },
                })}
              />
            </div>
          </>
        ) : null}
      </section>
      <button type="button" className={`${styles.button} ${styles.buttonDanger}`} onClick={onDelete}>{uiText("删除关系")}</button>
    </>
  );
}

/** Render configuration and checks as separate, mounted reading surfaces.
 * Args: catalog provides authoritative implementation contracts.
 * Returns: An Inspector that preserves buffered inputs when changing views.
 */
export function BuilderInspector({ catalog }: BuilderInspectorProps) {
  const uiLocale = useUiLocale();
  const panels = useBuilderPanels();
  const document = useAgentBuilderDocumentStore((state) => state.document);
  const selectedCanvasId = useAgentBuilderDocumentStore((state) => state.selectedCanvasId);
  const selectedEdgeId = useAgentBuilderDocumentStore((state) => state.selectedEdgeId);
  const compileResult = useAgentBuilderDocumentStore((state) => state.compileResult);
  const updateNode = useAgentBuilderDocumentStore((state) => state.updateNode);
  const updateCandidateProperty = useAgentBuilderDocumentStore((state) => state.updateCandidateProperty);
  const removeNodes = useAgentBuilderDocumentStore((state) => state.removeNodes);
  const updateEdge = useAgentBuilderDocumentStore((state) => state.updateEdge);
  const removeEdges = useAgentBuilderDocumentStore((state) => state.removeEdges);
  const node = useMemo(
    () => document?.capabilities.find((item) => item.canvasId === selectedCanvasId),
    [document, selectedCanvasId, uiLocale],
  );
  const relation = useMemo(
    () => document?.relations.find((item) => item.canvasId === selectedEdgeId),
    [document, selectedEdgeId, uiLocale],
  );
  const boundary = document && selectedCanvasId
    ? [document.input, document.output].find((item) => item.canvasId === selectedCanvasId)
    : undefined;
  // Keep configuration mounted across tabs so unfinished raw fields remain intact.
  useEffect(() => {
    if (compileResult?.isSuccess === false) panels.show("checks");
    // Navigate only for a new result, never on tab switches.
  }, [compileResult]);
  return (
    <aside className={styles.inspector} aria-label={uiText("Agent 能力 Inspector")}>
      <div className={styles.inspectorHeader}>
        <div className={styles.panelHeading}><h2>{panels.view === "checks" ? uiText("流程检查") : relation ? uiText("连接设置") : node || boundary ? uiText("节点配置") : uiText("Agent 概览")}</h2>
          {panels.close ? <button type="button" className={styles.panelClose} onClick={panels.close} aria-label={uiText("关闭配置面板")}>×</button> : null}
        </div>
        <div className={styles.inspectorTabs} role="group" aria-label={uiText("配置与检查视图")}>
          <button type="button" aria-pressed={panels.view === "configuration"} onClick={() => panels.show("configuration")}>{uiText("配置")}</button>
          <button type="button" aria-pressed={panels.view === "checks"} onClick={() => panels.show("checks")}>{uiText("检查")}{compileResult?.diagnostics.length ? ` · ${compileResult.diagnostics.length}` : ""}</button>
        </div>
      </div>
      <div hidden={panels.view !== "configuration"}>
      {boundary ? (
        <section className={styles.inspectorSection}>
          <h3 className={styles.sectionTitle}>{boundary.kind === "input" ? "Input" : "Output"}</h3>
          <p className={styles.muted}>
            {boundary.kind === "input"
              ? uiText("系统提供的唯一 Agent 入口；没有实现、依赖或设备权限。")
              : uiText("系统提供的唯一结束边界；普通连线表示连接的能力可以结束本次 Agent，不承诺输出 payload。")}
          </p>
          <p className={styles.muted}>{uiText("该边界可移动、选择和连线，但不能删除或复制。")}</p>
        </section>
      ) : node ? (
        <CapabilityInspector
          key={node.canvasId}
          node={node}
          catalog={catalog}
          onUpdate={(next) => updateNode(node.canvasId, () => next)}
          onCandidatePropertyChange={(candidateIndex, value, property = "params") => updateCandidateProperty(node.canvasId, candidateIndex, property, value)}
          onDelete={() => removeNodes([node.canvasId])}
        />
      ) : relation ? (
        <RelationInspector
          relation={relation}
          document={document!}
          catalog={catalog}
          onUpdate={(next) => updateEdge(relation.canvasId, () => next)}
          onDelete={() => removeEdges([relation.canvasId])}
        />
      ) : (
        <section className={styles.inspectorGuide} aria-label={uiText("Inspector 使用提示")}>
          <h3>{document?.name ?? uiText("开始搭建 Agent")}</h3>
          <p>{uiText("选择一个节点，查看它的用途和配置；选择连线，查看数据来源与反馈条件。")}</p>
          <dl className={styles.overviewCounts}>
            <div><dt>{uiText("能力")}</dt><dd>{document?.capabilities.length ?? 0}</dd></div>
            <div><dt>{uiText("连接")}</dt><dd>{document?.relations.length ?? 0}</dd></div>
          </dl>
          <p className={styles.muted}>{document?.capabilities.length ? uiText("已有示例可切换到运行页检查并试跑；需要修改时，选择画布中的能力。") : uiText("点击“添加能力”，开始搭建。")}</p>
        </section>
      )}
      </div>
      <section hidden={panels.view !== "checks"} className={styles.checksPanel} aria-label={uiText("检查结果")}>
        <h3 className={styles.sectionTitle}>{uiText("检查结果")}</h3>
        {document?.capabilities.length === 0 && compileResult?.diagnostics.length ? (
          <p className={styles.callout}>{uiText("这是空白 Agent 的起始状态。先添加 Perception、Memory、Reasoning 和 Action Executor；再把 Action Executor.result 连到 Memory.write 形成“下一轮反馈”。Output 暂时没有可达路径是预期的，完成闭环后再检查流程。")}</p>
        ) : compileResult?.diagnostics.length ? (
          <ul className={styles.diagnosticList}>
            {compileResult.diagnostics.map((item, index) => {
              const target = document ? diagnosticTarget(item, document, compileResult) : null;
              return (
              <li className={styles.diagnosticItem} data-severity={item.severity} key={`${item.code}-${index}`}>
                <span>{item.message}</span>
                <p>{diagnosticAdvice(item.code, { nodeId: item.nodeId, portId: item.portId })}</p>
                <small>{target ? uiMessage`对象：${target.id} · 暂不支持定位到具体字段` : uiText("流程级问题 · 暂无具体位置")}</small>
                <div className={styles.diagnosticActions}>
                {target ? <button type="button" className={styles.button} onClick={() => {
                  const state = useAgentBuilderDocumentStore.getState();
                  if (state.compileResult !== compileResult || state.document !== document) return;
                  try { state.prepareSnapshot(); } catch { return; }
                  panels.show("configuration");
                  if (target.kind === "node") {
                    state.selectNode(target.id);
                    const port = useCanvasInteractionStore.getState().port;
                    if (port?.sessionId === state.sessionId) port.reveal(target.id);
                  } else {
                    state.selectEdge(target.id);
                    const port = useCanvasInteractionStore.getState().port;
                    if (port?.sessionId === state.sessionId) port.reveal(target.id);
                  }
                }}>{uiText("查看对象")}</button> : null}
                <a href="/help?topic=validation" target="_blank" rel="noopener noreferrer">{uiText("检查帮助 ↗")}</a>
                </div>
                <details><summary>{uiText("技术详情")}</summary><code>{item.code}</code><p>{uiText("级别：")}{item.severity}</p></details>
              </li>
              );
            })}
          </ul>
        ) : <p className={styles.muted}>{compileResult?.isSuccess ? uiText("流程检查通过，未发现问题。") : uiText("点击“检查流程”查看问题与修改建议。")}</p>}
      </section>
    </aside>
  );
}
