import { isRecord, type JsonValue } from "@/shared/lib";
import type { StudioRunTask } from "@/entities/run";

export type AgentRunTarget = {
  agentId: string;
  revisionId: string;
  canonicalHash: string;
};

export type PreparedTaskRun = {
  task: StudioRunTask;
  semanticIdentity: string;
};

/** Serialize detached JSON with stable object-key ordering for retry identity. */
export function stableTaskJson(value: JsonValue): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableTaskJson).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableTaskJson(value[key]!)}`)
    .join(",")}}`;
}

/** Generate one opaque backend-compatible task-launch request identity. */
export function newTaskRunRequestId(): string {
  const random = globalThis.crypto?.randomUUID?.().replaceAll("-", "");
  return `studio-launch-${random ?? `${Date.now()}-${Math.random()}`}`;
}

/** Validate one ordinary task draft and derive its target-bound semantic identity.
 *
 * Args:
 *   target: Exact immutable Agent revision selected for execution.
 *   deviceProfileId: Safe server-owned Profile identity selected for this Run.
 *   taskText: User-entered ordinary task text.
 *   metadataText: Optional JSON object text passed through the existing Run contract.
 *
 * Returns:
 *   The detached Run task and a deterministic identity used only for safe retries.
 *
 * Raises:
 *   Error: The task is empty, metadata is too large/invalid, or its root is not an object.
 */
export function prepareTaskRun(
  target: AgentRunTarget,
  deviceProfileId: string,
  taskText: string,
  metadataText: string,
): PreparedTaskRun {
  if (!deviceProfileId) throw new Error("请选择当前服务提供的 Device Profile。");
  const text = taskText.trim();
  if (!text) throw new Error("请输入普通 Agent task；这里不是 BenchmarkTask。");
  if (new TextEncoder().encode(metadataText).byteLength > 16 * 1024) {
    throw new Error("metadata JSON 超过 16 KiB。");
  }
  let metadata: JsonValue;
  try {
    metadata = JSON.parse(metadataText) as JsonValue;
  } catch {
    throw new Error("metadata 必须是有效 JSON。");
  }
  if (!isRecord(metadata)) throw new Error("metadata JSON 根必须是对象。");
  const task = { text, metadata };
  return {
    task,
    semanticIdentity: [
      target.agentId,
      target.revisionId,
      target.canonicalHash,
      deviceProfileId,
      text,
      stableTaskJson(metadata),
    ].join("\u0000"),
  };
}
