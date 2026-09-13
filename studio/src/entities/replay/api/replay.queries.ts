import { useQuery } from "@tanstack/react-query";
import { getReplay, listReplays } from "./replayApi";

/** Query one page of persisted Replay History resources. */
export function useReplayPage(limit = 50, cursor?: string, agentId?: string) {
  return useQuery({
    queryKey: ["studio", "replays", { limit, cursor: cursor ?? null, agentId: agentId ?? null }],
    queryFn: () => listReplays(limit, cursor, agentId),
  });
}

/** Query one immutable Replay by stable route identity. */
export function useReplay(runId: string) {
  return useQuery({
    queryKey: ["studio", "replay", runId],
    queryFn: () => getReplay(runId),
    enabled: runId.length > 0,
  });
}
