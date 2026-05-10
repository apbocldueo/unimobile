import type { BenchmarkDraft } from "./types";

/** 将 Benchmark 草稿序列化为后端 DSL JSON（占位实现）。 */
export function serializeBenchmarkDraft(_draft: BenchmarkDraft): string {
  return JSON.stringify(_draft, null, 2);
}
