import type { ReplayMoment } from "@/entities/replay";
import type { ReplaySpeed } from "../model/playback.store";

const MIN_DELAY_MS = 180;
const MAX_DELAY_MS = 1_600;
const DEFAULT_DELAY_MS = 520;

/** Map recorded time to bounded visual delay without modifying Runtime facts. */
export function replayDelayMs(
  current: ReplayMoment | undefined,
  next: ReplayMoment | undefined,
  speed: ReplaySpeed,
): number {
  const timestampGap =
    current?.timestamp !== null
    && current?.timestamp !== undefined
    && next?.timestamp !== null
    && next?.timestamp !== undefined
      ? (next.timestamp - current.timestamp) * 1_000
      : null;
  const recorded =
    timestampGap !== null && timestampGap > 0
      ? timestampGap
      : current?.durationMs && current.durationMs > 0
        ? current.durationMs
        : DEFAULT_DELAY_MS;
  return Math.round(
    Math.min(MAX_DELAY_MS, Math.max(MIN_DELAY_MS, recorded)) / speed,
  );
}
