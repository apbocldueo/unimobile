import { useEffect, useMemo, useState } from "react";
import type { ComponentCatalog, ComponentCatalogItem } from "@/entities/component-catalog";
import type {
  StudioCapabilityNode,
  StudioCapabilityRelation,
  StudioDiagnostic,
  StudioFlowDocument,
} from "@/entities/agent-graph";
import type { JsonValue } from "@/shared/lib";
import { assertSecretRefSafe } from "../model/llmDependencies";
import { componentForNode } from "../model/flowAdapter";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import styles from "./agentBuilder.module.css";

type BuilderInspectorProps = { catalog: ComponentCatalog | null };

function JsonField({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: unknown;
  onCommit: (value: Record<string, JsonValue>) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
    setError(null);
  }, [value]);
  return (
    <div className={styles.field}>
      <label>{label}</label>
      <textarea
        aria-label={label}
        className={styles.textarea}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => {
          try {
            const parsed = JSON.parse(text) as unknown;
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
              throw new Error("必须是 JSON object");
            }
            assertSecretRefSafe(parsed, label);
            onCommit(parsed as Record<string, JsonValue>);
            setError(null);
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : "JSON 无效");
          }
        }}
      />
      {error ? <span className={styles.errorText}>{error}</span> : null}
    </div>
  );
}

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
    params: {},
    dependencies: {},
  };
  return { ...node, implementation: { ...node.implementation, candidates } };
}

function CapabilityInspector({
  node,
  catalog,
  onUpdate,
  onDelete,
}: {
  node: StudioCapabilityNode;
  catalog: ComponentCatalog | null;
  onUpdate: (node: StudioCapabilityNode) => void;
  onDelete: () => void;
}) {
  const choices = implementations(catalog, node);
  const selected = componentForNode(node, catalog);
  const first = node.implementation.candidates[0]!;
  return (
    <>
      <section className={styles.inspectorSection}>
        <h3 className={styles.sectionTitle}>Capability</h3>
        <dl className={styles.definitionList}>
          <div><dt>Family</dt><dd>{node.family}</dd></div>
          <div><dt>Logical ID</dt><dd>{node.logicalId}</dd></div>
        </dl>
      </section>
      <section className={styles.inspectorSection}>
        <h3 className={styles.sectionTitle}>Implementation</h3>
        <div className={styles.field}>
          <label>Exact implementation / version</label>
          <select
            aria-label="Exact implementation / version"
            className={styles.select}
            value={selected?.identifier ?? ""}
            onChange={(event) => {
              const component = choices.find((item) => item.identifier === event.target.value);
              if (component) onUpdate(replaceCandidate(node, 0, component));
            }}
          >
            {!selected ? <option value="">Unavailable selection</option> : null}
            {choices.map((item) => <option key={item.identifier} value={item.identifier}>{item.display.label} · {item.version}</option>)}
          </select>
        </div>
        <div className={styles.field}>
          <label>Binding policy</label>
          <select
            aria-label="Binding policy"
            className={styles.select}
            value={node.implementation.policy}
            onChange={(event) => {
              const policy = event.target.value as "single" | "fallback";
              if (policy === "single") {
                onUpdate({ ...node, implementation: { policy, candidates: [first] } });
                return;
              }
              const fallback = choices.find((item) => item.identifier !== selected?.identifier) ?? selected;
              if (!fallback) return;
              onUpdate({
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
        {node.implementation.candidates.map((candidate, index) => (
          <div key={`${candidate.namespace}:${candidate.name}:${index}`} className={styles.repairCard}>
            <strong>{index === 0 ? "Primary" : `Fallback ${index}`} · {candidate.namespace}:{candidate.name}@{candidate.version}</strong>
            {index > 0 ? (
              <select
                aria-label={`Fallback ${index} implementation`}
                className={styles.select}
                value={`${candidate.namespace}:${candidate.name}@${candidate.version}`}
                onChange={(event) => {
                  const component = choices.find((item) => item.identifier === event.target.value);
                  if (component) onUpdate(replaceCandidate(node, index, component));
                }}
              >
                {choices.map((item) => <option key={item.identifier} value={item.identifier}>{item.display.label} · {item.version}</option>)}
              </select>
            ) : null}
            <JsonField
              label={`Candidate ${index + 1} config`}
              value={candidate.params}
              onCommit={(params) => {
                const candidates = [...node.implementation.candidates];
                candidates[index] = { ...candidate, params };
                onUpdate({ ...node, implementation: { ...node.implementation, candidates } });
              }}
            />
            <JsonField
              label={`Candidate ${index + 1} dependencies`}
              value={candidate.dependencies}
              onCommit={(dependencies) => {
                const candidates = [...node.implementation.candidates];
                candidates[index] = { ...candidate, dependencies };
                onUpdate({ ...node, implementation: { ...node.implementation, candidates } });
              }}
            />
          </div>
        ))}
      </section>
      <button type="button" className={`${styles.button} ${styles.buttonDanger}`} onClick={onDelete}>
        删除能力实例
      </button>
    </>
  );
}

function RelationInspector({
  relation,
  onUpdate,
  onDelete,
}: {
  relation: StudioCapabilityRelation;
  onUpdate: (relation: StudioCapabilityRelation) => void;
  onDelete: () => void;
}) {
  return (
    <>
      <section className={styles.inspectorSection}>
        <h3 className={styles.sectionTitle}>Typed relation</h3>
        <dl className={styles.definitionList}>
          <div><dt>Kind</dt><dd>{relation.kind}</dd></div>
          <div><dt>Source</dt><dd>{relation.source.ownerId}.{relation.source.portId}</dd></div>
          <div><dt>Target</dt><dd>{relation.target.ownerId}</dd></div>
        </dl>
        {relation.kind === "feedback" && relation.feedback ? (
          <div className={styles.field}>
            <label>Maximum feedback iterations</label>
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
        ) : null}
      </section>
      <button type="button" className={`${styles.button} ${styles.buttonDanger}`} onClick={onDelete}>删除关系</button>
    </>
  );
}

function diagnosticOwner(
  diagnostic: StudioDiagnostic,
  document: StudioFlowDocument,
): string {
  const path = diagnostic.path ?? [];
  if (path[0] === "capabilities" && typeof path[1] === "number") {
    return document.capabilities[path[1]]?.logicalId ?? "document";
  }
  if (path[0] === "relations" && typeof path[1] === "number") {
    return document.relations[path[1]]?.canvasId ?? "document";
  }
  return "document";
}

/** Render implementation/dependency editing and exact diagnostics outside the canvas. */
export function BuilderInspector({ catalog }: BuilderInspectorProps) {
  const document = useAgentBuilderDocumentStore((state) => state.document);
  const selectedCanvasId = useAgentBuilderDocumentStore((state) => state.selectedCanvasId);
  const selectedEdgeId = useAgentBuilderDocumentStore((state) => state.selectedEdgeId);
  const compileResult = useAgentBuilderDocumentStore((state) => state.compileResult);
  const updateNode = useAgentBuilderDocumentStore((state) => state.updateNode);
  const removeNodes = useAgentBuilderDocumentStore((state) => state.removeNodes);
  const updateEdge = useAgentBuilderDocumentStore((state) => state.updateEdge);
  const removeEdges = useAgentBuilderDocumentStore((state) => state.removeEdges);
  const node = useMemo(
    () => document?.capabilities.find((item) => item.canvasId === selectedCanvasId),
    [document, selectedCanvasId],
  );
  const relation = useMemo(
    () => document?.relations.find((item) => item.canvasId === selectedEdgeId),
    [document, selectedEdgeId],
  );
  const boundary = document && selectedCanvasId
    ? [document.input, document.output].find((item) => item.canvasId === selectedCanvasId)
    : undefined;
  return (
    <aside className={styles.inspector} aria-label="Agent 能力 Inspector">
      <div className={styles.panelHeading}><div><h2>Inspector</h2><p>实现选择、依赖与执行细节</p></div></div>
      {boundary ? (
        <section className={styles.inspectorSection}>
          <h3 className={styles.sectionTitle}>{boundary.kind === "input" ? "Input" : "Output"}</h3>
          <p className={styles.muted}>
            {boundary.kind === "input"
              ? "系统提供的唯一 Agent 入口；没有实现、依赖或设备权限。"
              : "系统提供的唯一结束边界；普通连线表示连接的能力可以结束本次 Agent，不承诺输出 payload。"}
          </p>
          <p className={styles.muted}>该边界可移动、选择和连线，但不能删除或复制。</p>
        </section>
      ) : node ? (
        <CapabilityInspector
          node={node}
          catalog={catalog}
          onUpdate={(next) => updateNode(node.canvasId, () => next)}
          onDelete={() => removeNodes([node.canvasId])}
        />
      ) : relation ? (
        <RelationInspector
          relation={relation}
          onUpdate={(next) => updateEdge(relation.canvasId, () => next)}
          onDelete={() => removeEdges([relation.canvasId])}
        />
      ) : (
        <p className={styles.muted}>选择一个能力、边界或关系查看详细信息。</p>
      )}
      <section className={styles.inspectorSection}>
        <h3 className={styles.sectionTitle}>Validation</h3>
        {compileResult?.diagnostics.length ? (
          <ul className={styles.diagnosticList}>
            {compileResult.diagnostics.map((item, index) => (
              <li key={`${item.code}-${index}`}>
                <strong>{item.code}</strong>
                <span>{item.message}</span>
                {document ? <small>Owner: {diagnosticOwner(item, document)}</small> : null}
              </li>
            ))}
          </ul>
        ) : <p className={styles.muted}>尚无诊断。Validate 后这里会保留 exact generated identity 与能力归属。</p>}
      </section>
    </aside>
  );
}
