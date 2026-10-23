import { studioRequest } from "@/shared/api";
import { parseReplayEnvelope, parseReplayPage, type ReplayEnvelope, type ReplayPage } from "../model/replay.schema";

/** List real persisted Replay resources through bounded cursor pagination. */
export async function listReplays(
  limit = 50,
  cursor?: string,
  agentId?: string,
): Promise<ReplayPage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  if (agentId) query.set("agentId", agentId);
  return parseReplayPage(
    await studioRequest(`/api/studio/replays?${query.toString()}`),
  );
}

/** Load and strictly parse one immutable Replay envelope. */
export async function getReplay(runId: string): Promise<ReplayEnvelope> {
  return parseReplayEnvelope(
    await studioRequest(`/api/studio/replays/${encodeURIComponent(runId)}`),
  );
}
