import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";

export type BenchmarkPhase = {
  phase: string;
  status: string;
  durationMs: number | null;
  errorCode: string;
  message: string;
  evidence: JsonValue;
};

export type BenchmarkContext = {
  experimentId: string;
  taskId: string;
  agentId: string;
  repeat: number;
  outcome: "pass" | "fail" | "invalid" | "skipped";
  identities: Record<string, string>;
  phases: BenchmarkPhase[];
  evaluation: JsonValue | null;
};

/** Parse one Benchmark lifecycle phase. */
function parseBenchmarkPhase(value: unknown, path: string): BenchmarkPhase {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["phase", "status", "durationMs", "errorCode", "message", "evidence"],
    path,
  );
  return {
    phase: requireString(value.phase, `${path}.phase`),
    status: requireString(value.status, `${path}.status`),
    durationMs:
      value.durationMs === null || value.durationMs === undefined
        ? null
        : requireNumber(value.durationMs, `${path}.durationMs`),
    errorCode: typeof value.errorCode === "string" ? value.errorCode : "",
    message: typeof value.message === "string" ? value.message : "",
    evidence: cloneJson(value.evidence ?? {}, `${path}.evidence`),
  };
}

/** Parse optional Benchmark context independently from the Agent result. */
export function parseBenchmarkContext(
  value: unknown,
  path = "benchmark",
): BenchmarkContext | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "experimentId",
      "taskId",
      "agentId",
      "repeat",
      "outcome",
      "identities",
      "phases",
      "evaluation",
    ],
    path,
  );
  const outcome = requireString(value.outcome, `${path}.outcome`);
  if (!["pass", "fail", "invalid", "skipped"].includes(outcome)) {
    throw new Error(`${path}.outcome is unsupported`);
  }
  if (!isRecord(value.identities)) throw new Error(`${path}.identities must be an object`);
  const identities = Object.fromEntries(
    Object.entries(value.identities).map(([key, item]) => [
      key,
      requireString(item, `${path}.identities.${key}`),
    ]),
  );
  return {
    experimentId: requireString(value.experimentId, `${path}.experimentId`),
    taskId: requireString(value.taskId, `${path}.taskId`),
    agentId: requireString(value.agentId, `${path}.agentId`),
    repeat: requireNumber(value.repeat, `${path}.repeat`),
    outcome: outcome as BenchmarkContext["outcome"],
    identities,
    phases: Array.isArray(value.phases)
      ? value.phases.map((item, index) =>
          parseBenchmarkPhase(item, `${path}.phases[${index}]`),
        )
      : [],
    evaluation:
      value.evaluation === null || value.evaluation === undefined
        ? null
        : cloneJson(value.evaluation, `${path}.evaluation`),
  };
}
