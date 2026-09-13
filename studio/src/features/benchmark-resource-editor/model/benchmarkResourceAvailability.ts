import type { StudioHeadResponse } from "@/shared/api";
import { StudioApiError, StudioHeadContractError } from "@/shared/api";

export type BenchmarkResourceAvailability =
  | { state: "unchecked" }
  | { state: "pending" }
  | { state: "readable"; head: StudioHeadResponse }
  | { state: "missing" }
  | { state: "unavailable"; message: string }
  | { state: "contract-failure"; message: string };

export type BenchmarkResourceAvailabilityInput = {
  enabled: boolean;
  pending: boolean;
  data?: StudioHeadResponse;
  error?: unknown;
};

/** Project one selected resource HEAD query into truthful UI facts. */
export function projectBenchmarkResourceAvailability(
  input: BenchmarkResourceAvailabilityInput,
): BenchmarkResourceAvailability {
  if (!input.enabled) return { state: "unchecked" };
  if (input.pending) return { state: "pending" };
  if (input.data) return { state: "readable", head: input.data };
  if (input.error instanceof StudioApiError && input.error.status === 404) {
    return { state: "missing" };
  }
  if (input.error instanceof StudioHeadContractError) {
    return {
      state: "contract-failure",
      message: `响应头完整性校验失败：${input.error.kind}`,
    };
  }
  return {
    state: "unavailable",
    message:
      input.error instanceof Error
        ? input.error.message
        : "资源可用性暂时无法确认。",
  };
}
