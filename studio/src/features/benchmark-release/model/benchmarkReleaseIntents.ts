import type { BenchmarkReleaseCommand } from "@/entities/benchmark-authoring";

export type BenchmarkReleaseOperation = "freeze" | "publish" | "export";

export type BenchmarkReleaseIntent = {
  operation: BenchmarkReleaseOperation;
  draftId: string;
  targetId: string;
  command: BenchmarkReleaseCommand;
};

/** Generate one browser-safe durable release command identity. */
export function createBenchmarkReleaseIntentId(): string {
  return `benchmark-release-${crypto.randomUUID()}`;
}

/** Preserve one command ID only while operation, owner, and target are unchanged. */
export function prepareBenchmarkReleaseIntent(
  current: BenchmarkReleaseIntent | null,
  semantic: {
    operation: BenchmarkReleaseOperation;
    draftId: string;
    targetId: string;
  },
  createIdentity: () => string = createBenchmarkReleaseIntentId,
): BenchmarkReleaseIntent {
  if (
    current
    && current.operation === semantic.operation
    && current.draftId === semantic.draftId
    && current.targetId === semantic.targetId
  ) {
    return current;
  }
  return {
    ...semantic,
    command: {
      schemaVersion: 1,
      clientRequestId: createIdentity(),
    },
  };
}
