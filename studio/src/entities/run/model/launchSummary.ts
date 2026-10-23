import { uiText } from "@/shared/i18n";
import { isRecord } from "@/shared/lib";
import type { RunSnapshot } from "./run.schema";

/** Project only declared model names and budgets; never display dependency credentials.
 * @param snapshot Verified immutable launch snapshot.
 * @returns Bounded presentation facts, or explicit unavailable values for legacy graphs.
 */
export function launchSummary(snapshot: RunSnapshot) {
  const document = snapshot.capabilityDocument;
  if (document?.schemaVersion !== 3) return { models: [], maxSteps: null, maxFeedbackIterations: null };
  const models = document.capabilities.flatMap((node) => node.implementation.candidates.flatMap((candidate) => {
    const llm = candidate.dependencies.llm;
    if (!isRecord(llm) || !isRecord(llm.params) || typeof llm.params.model !== "string") return [];
    return [`${node.logicalId} · ${llm.params.model.slice(0, 160)}`];
  }));
  return { models: [...new Set(models)].slice(0, 20), maxSteps: document.policies.maxSteps, maxFeedbackIterations: document.policies.maxFeedbackIterations };
}

/** Translate a known runtime stop fact without inferring a model/device root cause. */
export function describeRunStop(error: string): string {
  if (error === "Generalized feedback exhausted its iteration budget") {
    return uiText("反馈循环次数已用尽，任务尚未完成。请查看最后截图与动作，调整任务或流程后重试。");
  }
  return error;
}
