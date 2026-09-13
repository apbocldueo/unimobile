import type {
  ActivationProjection,
  DebugEvidenceReference,
  ReplayProjection,
  RunAction,
  RunSnapshot,
} from "@/entities/run";
import type { JsonValue } from "@/shared/lib";

export type StoryStepStatus = "running" | "success" | "failure" | "skipped";

export type StoryFact = {
  key: string;
  label: string;
  value: JsonValue;
  artifactId?: string | null;
  availability?: string;
};

export type StoryStep = {
  stepId: string;
  interactionStep: number;
  ownerKind: "capability" | "relation" | "activation" | "terminal";
  ownerId: string;
  role: string;
  roleLabel: string;
  verb: string;
  title: string;
  summary: string;
  status: StoryStepStatus;
  inputs: StoryFact[];
  outputs: StoryFact[];
  activationIds: string[];
  primaryActivationId: string | null;
  startCursor: number;
  endCursor: number | null;
  durationMs: number | null;
  error: string;
  modelResponse: DebugEvidenceReference | null;
  modelResponseAvailability: string;
  promptAvailability: string;
};

export type RunStory = {
  steps: StoryStep[];
  currentStepId: string | null;
  unmappedActivationIds: string[];
  truncatedStepCount: number;
};

export type RunStoryOptions = {
  terminalVisible?: boolean;
  agentStatus?: string;
  resultError?: string;
  maximumSteps?: number;
};

type OwnerResolution = {
  ownerKind: StoryStep["ownerKind"];
  ownerId: string;
  role: string;
  groupable: boolean;
};

const STORY_ROLES = new Set([
  "perception",
  "planner",
  "reasoning",
  "memory",
  "action_executor",
  "verifier",
  "grounder",
  "tool",
]);

const ROLE_COPY: Record<string, Pick<StoryStep, "roleLabel" | "verb" | "title">> = {
  perception: { roleLabel: "感知", verb: "看见", title: "读取并理解设备画面" },
  planner: { roleLabel: "规划", verb: "规划", title: "形成执行计划" },
  reasoning: { roleLabel: "推理", verb: "判断", title: "选择下一步行动" },
  memory: { roleLabel: "记忆", verb: "记住", title: "读取或更新运行上下文" },
  action_executor: { roleLabel: "动作执行", verb: "行动", title: "执行设备动作" },
  verifier: { roleLabel: "验证", verb: "检查", title: "检查目标是否满足" },
  grounder: { roleLabel: "定位", verb: "定位", title: "把目标定位到界面" },
  tool: { roleLabel: "工具", verb: "调用", title: "调用外部工具" },
  feedback: { roleLabel: "反馈", verb: "继续", title: "进入下一轮观察与判断" },
  flow: { roleLabel: "流程", verb: "衔接", title: "进入下一步" },
  termination: { roleLabel: "完成检查", verb: "检查", title: "检查运行是否可以结束" },
  external: { roleLabel: "扩展组件", verb: "处理", title: "执行扩展组件" },
  terminal: { roleLabel: "运行结果", verb: "完成", title: "运行已经结束" },
};

const FACT_LABELS: Record<string, string> = {
  task: "任务",
  observation: "设备观察",
  screenshot: "屏幕截图",
  dimensions: "屏幕尺寸",
  elements: "界面元素",
  detections: "识别结果",
  recognized: "识别内容",
  representation: "画面描述",
  perception: "感知结果",
  plan: "计划",
  goal: "目标",
  step: "计划步骤",
  replan: "重新规划",
  memory: "记忆摘要",
  context: "上下文",
  read: "读取内容",
  write: "写入内容",
  fragment: "记忆变化",
  reasoning: "判断过程",
  thought: "判断依据",
  decision: "决策",
  action: "动作",
  action_type: "动作类型",
  params: "动作参数",
  target: "动作目标",
  coordinate: "目标坐标",
  result: "执行结果",
  effect: "设备效果",
  status: "状态",
  verification: "验证结果",
  verdict: "结论",
  feedback: "反馈",
  evidence: "验证证据",
};

const INTERNAL_FACT_KEYS = new Set([
  "causal_index",
  "component",
  "cursor",
  "duration",
  "duration_ms",
  "interaction_step",
  "kind",
  "loop_iteration",
  "loop_path",
  "node_path",
  "payload",
  "phase",
  "role",
  "sequence",
  "source_sequence",
  "stage",
  "timestamp",
]);

/** Normalize a formal role identifier without using component class-name guesses. */
function normalizeRole(role: string): string {
  const tail = role.split(".").at(-1) ?? "";
  return tail
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[-\s]+/g, "_");
}

/** Return whether a JSON value contains reader-visible content. */
function hasContent(value: JsonValue): boolean {
  if (value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

/** Remove Prompt-shaped fields recursively before any presentation fallback. */
function redactPromptFields(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(redactPromptFields);
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !key.toLowerCase().includes("prompt"))
      .map(([key, item]) => [key, redactPromptFields(item)]),
  );
}

/** Normalize one payload field name so internal identity keys can be recognized safely. */
function normalizeFactKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[-\s]+/g, "_");
}

/** Return whether a primitive string is shaped like an internal runtime identity. */
function looksLikeInternalIdentifier(value: string): boolean {
  const candidate = value.trim();
  return /^(?:a\d+|run|activation|moment|observation|action|artifact|revision|debug|device)-[a-z0-9:_-]{6,}$/i.test(candidate)
    || /^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(candidate)
    || /^sha256:[0-9a-f]{16,}$/i.test(candidate)
    || /^(?:studio_generated|zhixing|component|plugin)\./i.test(candidate)
    || STORY_ROLES.has(normalizeFactKey(candidate))
    || ["input", "output"].includes(normalizeFactKey(candidate));
}

/** Remove internal identifiers and bookkeeping fields from reader-facing facts only. */
function sanitizeReaderValue(value: JsonValue): JsonValue {
  if (typeof value === "string") return looksLikeInternalIdentifier(value) ? null : value;
  if (Array.isArray(value)) {
    return value.map(sanitizeReaderValue).filter(hasContent);
  }
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, item]) => {
      const normalizedKey = normalizeFactKey(key);
      if (INTERNAL_FACT_KEYS.has(normalizedKey) || /(?:^|_)(?:id|ids|hash)$/.test(normalizedKey)) {
        return [];
      }
      const sanitized = sanitizeReaderValue(item);
      return hasContent(sanitized) ? [[key, sanitized]] : [];
    }),
  );
}

/** Unwrap typed Debug Summary envelopes into their declared reader-facing values. */
function unwrapSummaryValues(value: JsonValue): JsonValue {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return value;
  for (const direction of ["inputs", "outputs"]) {
    const carrier = value[direction];
    if (typeof carrier !== "object" || carrier === null || Array.isArray(carrier)) continue;
    const values = carrier.values;
    if (typeof values === "object" && values !== null && !Array.isArray(values)) return values;
    if ("keys" in carrier || "type" in carrier) return null;
  }
  const payload = value.payload;
  if (
    typeof payload === "object"
    && payload !== null
    && !Array.isArray(payload)
    && ("phase" in value || "kind" in value || "interaction_step" in value)
  ) {
    return unwrapSummaryValues(payload);
  }
  return value;
}

/** Convert one safe summary into a bounded list of reader-facing facts. */
function factsFromValue(value: JsonValue, fallbackKey: string, fallbackLabel: string): StoryFact[] {
  const safe = sanitizeReaderValue(unwrapSummaryValues(redactPromptFields(value)));
  if (!hasContent(safe)) return [];
  if (typeof safe !== "object" || safe === null || Array.isArray(safe)) {
    return [{ key: fallbackKey, label: fallbackLabel, value: safe }];
  }
  return Object.entries(safe)
    .slice(0, 12)
    .map(([key, item]) => ({
      key,
      label: FACT_LABELS[key.toLowerCase()] ?? key.replaceAll("_", " "),
      value: item,
    }));
}

/** Serialize one value only for deterministic local deduplication. */
function stableValue(value: JsonValue): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableValue).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${key}:${stableValue(value[key]!)}`).join(",")}}`;
}

/** Merge facts while retaining causal first appearance and bounded content. */
function mergeFacts(current: StoryFact[], incoming: StoryFact[]): StoryFact[] {
  const seen = new Set(current.map((fact) => `${fact.key}:${stableValue(fact.value)}`));
  const merged = [...current];
  for (const fact of incoming) {
    const identity = `${fact.key}:${stableValue(fact.value)}`;
    if (seen.has(identity)) continue;
    seen.add(identity);
    merged.push(fact);
    if (merged.length >= 16) break;
  }
  return merged;
}

/** Locate the latest causally visible observation for one interaction. */
function observationForInteraction(projection: ReplayProjection, interactionStep: number) {
  for (const observationId of [...projection.visibleObservationIds].reverse()) {
    const observation = projection.observationsById[observationId];
    if (observation?.interactionStep === interactionStep) return observation;
  }
  return null;
}

/** Locate the latest causally visible action for one interaction. */
function actionForInteraction(
  projection: ReplayProjection,
  interactionStep: number,
): RunAction | null {
  for (const actionId of [...projection.visibleActionIds].reverse()) {
    const action = projection.actionsById[actionId];
    if (action?.interactionStep === interactionStep) return action;
  }
  return null;
}

/** Resolve one exact activation to a formal authoring owner or safe role fallback. */
function resolveOwner(snapshot: RunSnapshot, activation: ActivationProjection): OwnerResolution | null {
  const mapping = snapshot.projectionMap?.find(
    (entry) => entry.graphKind === "node" && entry.graphId === activation.nodeId,
  );
  if (mapping) {
    if (mapping.owner.kind === "capability" && mapping.owner.ownerId) {
      const document = snapshot.capabilityDocument;
      const capability = document?.schemaVersion === 3
        ? document.capabilities.find((item) => item.logicalId === mapping.owner.ownerId)
        : null;
      const role = capability?.family ?? normalizeRole(activation.role);
      if (!STORY_ROLES.has(role)) return null;
      return {
        ownerKind: "capability",
        ownerId: mapping.owner.ownerId,
        role,
        groupable: true,
      };
    }
    if (mapping.owner.kind === "relation" && mapping.owner.ownerId) {
      const document = snapshot.capabilityDocument;
      const relation = document?.schemaVersion === 3
        ? document.relations.find((item) => item.canvasId === mapping.owner.ownerId)
        : null;
      const role = relation?.kind === "feedback"
        ? "feedback"
        : relation?.kind === "termination"
          ? "termination"
          : relation?.kind === "activation"
            ? "flow"
            : null;
      return role ? {
        ownerKind: "relation",
        ownerId: mapping.owner.ownerId,
        role,
        groupable: true,
      } : null;
    }
    return null;
  }

  const role = normalizeRole(activation.role);
  if (["runtime_service", "observation_provider", "device_observe"].includes(role)) {
    return null;
  }
  return {
    ownerKind: "activation",
    ownerId: activation.nodeId || activation.activationId,
    role: STORY_ROLES.has(role) ? role : "external",
    groupable: false,
  };
}

/** Return role-aware input/output evidence for one exact activation. */
function activationEvidence(
  projection: ReplayProjection,
  activation: ActivationProjection,
  role: string,
): Pick<StoryStep, "inputs" | "outputs" | "error" | "modelResponse" | "modelResponseAvailability" | "promptAvailability"> {
  const debugHistory = projection.debugByActivationId[activation.activationId] ?? [];
  const firstDebug = debugHistory[0] ?? null;
  const latestDebug = debugHistory.at(-1) ?? null;
  let inputs: StoryFact[] = [];
  let outputs: StoryFact[] = [];

  if (firstDebug && hasContent(firstDebug.task)) {
    inputs = mergeFacts(inputs, factsFromValue(firstDebug.task, "task", "任务"));
  }
  if (firstDebug) {
    inputs = mergeFacts(inputs, factsFromValue(firstDebug.inputSummary, "input", "输入摘要"));
  }
  if (latestDebug) {
    outputs = mergeFacts(outputs, factsFromValue(latestDebug.outputSummary, "output", "输出摘要"));
  }

  if (inputs.length === 0 && activation.payloadHistory.length > 0) {
    inputs = factsFromValue(activation.payloadHistory[0]!, "input", "输入摘要");
  }
  if (outputs.length === 0 && activation.payloadHistory.length > 1) {
    outputs = factsFromValue(activation.payloadHistory.at(-1)!, "output", "输出摘要");
  }

  const observation = observationForInteraction(projection, activation.interactionStep);
  if (role === "perception" && observation) {
    if (observation.width > 0 && observation.height > 0) {
      inputs = mergeFacts(inputs, [{
        key: "dimensions",
        label: "屏幕尺寸",
        value: `${observation.width} × ${observation.height}`,
      }]);
    }
    if (observation.screenshotArtifactId) {
      inputs = mergeFacts(inputs, [{
        key: "screenshot",
        label: "屏幕截图",
        value: "已采集",
        artifactId: observation.screenshotArtifactId,
        availability: "available",
      }]);
    }
  }

  const action = actionForInteraction(projection, activation.interactionStep);
  if (role === "action_executor" && action) {
    inputs = mergeFacts(inputs, [{ key: "action_type", label: "动作类型", value: action.actionType }]);
    outputs = mergeFacts(outputs, [
      { key: "status", label: "执行状态", value: action.status },
      {
        key: "effect",
        label: "设备效果",
        value: action.effectPerformed
          ? `已确认：${action.effectKind || "已执行"}`
          : "未确认设备副作用",
      },
    ]);
  }

  return {
    inputs,
    outputs,
    error: latestDebug?.error || action?.error || "",
    modelResponse: latestDebug?.evidenceRefs.modelResponse ?? null,
    modelResponseAvailability:
      latestDebug?.evidenceRefs.modelResponse?.availability
      ?? latestDebug?.availability.modelResponse
      ?? "not_captured",
    promptAvailability: latestDebug?.availability.prompt ?? "not_captured",
  };
}

/** Produce a compact human summary from role-specific formal facts. */
function summarizeStep(
  role: string,
  status: StoryStepStatus,
  outputs: StoryFact[],
  action: RunAction | null,
  error: string,
): string {
  if (status === "failure") return error || "该步骤执行失败，技术详情中保留了正式错误。";
  if (status === "running") return "正在处理，已经到达的事实会继续保留。";
  if (role === "action_executor" && action) {
    return action.effectPerformed
      ? `${action.actionType} 已执行，设备效果已确认。`
      : `${action.actionType} 已返回，尚未确认设备副作用。`;
  }
  const preferred = role === "reasoning"
    ? ["decision", "action", "thought", "result"]
    : role === "perception"
      ? ["elements", "detections", "recognized", "representation", "perception"]
      : role === "memory"
        ? ["write", "fragment", "context", "result"]
        : role === "planner"
          ? ["plan", "step", "replan", "result"]
          : role === "verifier"
            ? ["verdict", "verification", "feedback", "result"]
            : ["result", "status", "output"];
  const preferredFact = preferred
    .map((key) => outputs.find((item) => item.key.toLowerCase() === key))
    .find(Boolean);
  const fact = preferredFact ?? (["external", "tool"].includes(role) ? outputs[0] : undefined);
  if (!fact) return status === "skipped" ? "该步骤有正式跳过事实。" : "该步骤已完成。";
  if (typeof fact.value === "string") return fact.value;
  if (Array.isArray(fact.value)) return `${fact.label}：${fact.value.length} 项`;
  if (typeof fact.value === "number" || typeof fact.value === "boolean") {
    return `${fact.label}：${String(fact.value)}`;
  }
  return `${fact.label}已记录，可在组件详情中查看。`;
}

/** Merge one exact activation into a reader-facing story step. */
function mergeActivation(
  existing: StoryStep | null,
  projection: ReplayProjection,
  activation: ActivationProjection,
  owner: OwnerResolution,
): StoryStep {
  const copy = ROLE_COPY[owner.role] ?? {
    ...ROLE_COPY.external,
    roleLabel: activation.role || activation.component || ROLE_COPY.external.roleLabel,
  };
  const evidence = activationEvidence(projection, activation, owner.role);
  const action = actionForInteraction(projection, activation.interactionStep);
  const statuses = [existing?.status, activation.status];
  const status: StoryStepStatus = statuses.includes("failure")
    ? "failure"
    : statuses.includes("running")
      ? "running"
      : statuses.includes("success")
        ? "success"
        : "skipped";
  const inputs = mergeFacts(existing?.inputs ?? [], evidence.inputs);
  const outputs = mergeFacts(existing?.outputs ?? [], evidence.outputs);
  const error = evidence.error || existing?.error || "";
  return {
    stepId: existing?.stepId
      ?? `${activation.interactionStep}:${owner.ownerKind}:${owner.ownerId}`,
    interactionStep: activation.interactionStep,
    ownerKind: owner.ownerKind,
    ownerId: owner.ownerId,
    role: owner.role,
    roleLabel: copy.roleLabel,
    verb: copy.verb,
    title: copy.title,
    summary: summarizeStep(owner.role, status, outputs, action, error),
    status,
    inputs,
    outputs,
    activationIds: [...(existing?.activationIds ?? []), activation.activationId],
    primaryActivationId: activation.activationId,
    startCursor: Math.min(existing?.startCursor ?? activation.startCursor, activation.startCursor),
    endCursor: activation.endCursor ?? existing?.endCursor ?? null,
    durationMs:
      activation.durationMs === null
        ? existing?.durationMs ?? null
        : (existing?.durationMs ?? 0) + activation.durationMs,
    error,
    modelResponse: evidence.modelResponse ?? existing?.modelResponse ?? null,
    modelResponseAvailability:
      evidence.modelResponseAvailability !== "not_captured"
        ? evidence.modelResponseAvailability
        : existing?.modelResponseAvailability ?? "not_captured",
    promptAvailability:
      evidence.promptAvailability !== "not_captured"
        ? evidence.promptAvailability
        : existing?.promptAvailability ?? "not_captured",
  };
}

/** Project immutable Run facts into a bounded component-level causal story.
 *
 * Args:
 *   snapshot: Exact immutable graph/capability snapshot used by the Run.
 *   projection: Current factual Live or Replay prefix projection.
 *   options: Presentation-only terminal visibility and size settings.
 *
 * Returns:
 *   A detached reader-facing story plus exact unmapped activation identities.
 */
export function selectRunStory(
  snapshot: RunSnapshot,
  projection: ReplayProjection,
  options: RunStoryOptions = {},
): RunStory {
  const byId = new Map<string, StoryStep>();
  const order: string[] = [];
  const unmappedActivationIds: string[] = [];

  for (const activationId of projection.activationOrder) {
    const activation = projection.activationsById[activationId];
    if (!activation) continue;
    const owner = resolveOwner(snapshot, activation);
    if (!owner) {
      unmappedActivationIds.push(activationId);
      continue;
    }
    const stepId = `${activation.interactionStep}:${owner.ownerKind}:${owner.ownerId}`;
    const existing = owner.groupable ? byId.get(stepId) ?? null : null;
    const step = mergeActivation(existing, projection, activation, owner);
    if (!byId.has(step.stepId)) order.push(step.stepId);
    byId.set(step.stepId, step);
  }

  if (options.terminalVisible) {
    const status = options.agentStatus || projection.agentStatus;
    const failed = !["success", "completed", "complete"].includes(status.toLowerCase());
    const copy = ROLE_COPY.terminal;
    const step: StoryStep = {
      stepId: `terminal:${projection.cursor}`,
      interactionStep: Math.max(projection.currentInteractionStep, 1),
      ownerKind: "terminal",
      ownerId: "terminal",
      role: "terminal",
      roleLabel: copy.roleLabel,
      verb: failed ? "结束" : copy.verb,
      title: failed ? "运行已结束，并保留了失败事实" : copy.title,
      summary: options.resultError || (failed ? `Agent 状态：${status}` : "Agent 已完成本次任务。"),
      status: failed ? "failure" : "success",
      inputs: [],
      outputs: [{ key: "status", label: "运行状态", value: status }],
      activationIds: [],
      primaryActivationId: null,
      startCursor: projection.cursor,
      endCursor: projection.cursor,
      durationMs: null,
      error: options.resultError ?? "",
      modelResponse: null,
      modelResponseAvailability: "not_captured",
      promptAvailability: "not_captured",
    };
    order.push(step.stepId);
    byId.set(step.stepId, step);
  }

  const allSteps = order.map((stepId) => byId.get(stepId)!).filter(Boolean);
  const maximumSteps = Math.max(10, options.maximumSteps ?? 80);
  const truncatedStepCount = Math.max(0, allSteps.length - maximumSteps);
  const steps = allSteps.slice(-maximumSteps);
  const currentActivationId = projection.currentActivationId;
  const current = currentActivationId
    ? [...steps].reverse().find((step) => step.activationIds.includes(currentActivationId))
    : null;
  return {
    steps,
    currentStepId: current?.stepId ?? steps.at(-1)?.stepId ?? null,
    unmappedActivationIds,
    truncatedStepCount,
  };
}
