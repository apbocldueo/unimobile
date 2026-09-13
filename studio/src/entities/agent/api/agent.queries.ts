import { queryOptions, useQuery } from "@tanstack/react-query";
import { getStudioAgent } from "./agentApi";

export const studioAgentKeys = {
  all: ["studio", "agents"] as const,
  detail: (agentId: string) => ["studio", "agent", agentId] as const,
};

/** Build the shared Agent metadata query without coupling display names to Run identity. */
export function studioAgentQueryOptions(agentId: string) {
  return queryOptions({
    queryKey: studioAgentKeys.detail(agentId),
    queryFn: () => getStudioAgent(agentId),
    enabled: agentId.length > 0,
    retry: false,
  });
}

/** Read mutable Agent metadata while leaving Run and Replay resources authoritative. */
export function useStudioAgent(agentId: string) {
  return useQuery(studioAgentQueryOptions(agentId));
}
