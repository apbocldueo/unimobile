import type { BenchmarkAuthoringDocument } from "@/entities/benchmark-authoring";
import { cloneJson, type JsonValue } from "@/shared/lib";

export type TaskBufferError = {
  message: string;
  line: number | null;
  column: number | null;
};

export type TaskBuffer = {
  text: string;
  appliedText: string;
  error: TaskBufferError | null;
};

export type TaskBufferMap = Record<string, TaskBuffer>;

/** Render parsed task arrays with one deterministic human-editable format. */
export function prettyTaskJson(tasks: JsonValue[]): string {
  return `${JSON.stringify(tasks, null, 2)}\n`;
}

/** Reconstruct isolated raw buffers from one strict parsed document. */
export function createTaskBuffers(
  document: BenchmarkAuthoringDocument,
): TaskBufferMap {
  return Object.fromEntries(
    document.taskFiles.map((file) => {
      const text = prettyTaskJson(file.tasks);
      return [file.path, { text, appliedText: text, error: null }];
    }),
  );
}

/** Derive line and column from JSON.parse's byte-position diagnostic. */
function errorLocation(
  text: string,
  error: unknown,
): TaskBufferError {
  const message = error instanceof Error ? error.message : "Invalid JSON";
  const match = /position\s+(\d+)/i.exec(message);
  if (!match) return { message, line: null, column: null };
  const position = Number(match[1]);
  const prefix = text.slice(0, position);
  const lines = prefix.split("\n");
  return {
    message,
    line: lines.length,
    column: (lines.at(-1)?.length ?? 0) + 1,
  };
}

/** Parse one raw task buffer as a detached safe JSON array.
 *
 * Args:
 *   text: Browser-local raw JSON text.
 *
 * Raises:
 *   Error: Text is invalid JSON, the root is not an array, or values are unsafe.
 *
 * Returns:
 *   A detached safe JSON task array.
 */
export function parseTaskBuffer(text: string): JsonValue[] {
  const parsed: unknown = JSON.parse(text);
  if (!Array.isArray(parsed)) throw new Error("Task JSON root must be an array");
  return parsed.map((item, index) => cloneJson(item, `tasks[${index}]`));
}

/** Parse one buffer without discarding the user's invalid local text. */
export function inspectTaskBuffer(
  buffer: TaskBuffer,
): { tasks: JsonValue[] | null; error: TaskBufferError | null } {
  try {
    return { tasks: parseTaskBuffer(buffer.text), error: null };
  } catch (error) {
    return { tasks: null, error: errorLocation(buffer.text, error) };
  }
}

/** Return whether text has not been explicitly applied to the parsed document. */
export function isTaskBufferUnapplied(buffer: TaskBuffer): boolean {
  return buffer.text !== buffer.appliedText;
}

/** Return whether any raw task text blocks a safe revision save. */
export function taskBuffersBlockSave(buffers: TaskBufferMap): boolean {
  return Object.values(buffers).some(
    (buffer) => buffer.error !== null || isTaskBufferUnapplied(buffer),
  );
}
