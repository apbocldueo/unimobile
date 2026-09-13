import { queryOptions, useQuery } from "@tanstack/react-query";
import {
  getExactRevisionReadiness,
  getRuntimeEnvironmentReadiness,
  getSafeDeviceProfiles,
} from "./runtimeReadinessApi";

export const runtimeReadinessKeys = {
  process: ["studio", "runtime-readiness"] as const,
  profiles: ["studio", "runtime-readiness", "device-profiles"] as const,
  exact: (agentId: string, revisionId: string, profileId: string) =>
    ["studio", "runtime-readiness", "exact", agentId, revisionId, profileId] as const,
};

/** Subscribe to the process projection through one shared Query cache key. */
export function useRuntimeEnvironmentReadiness() {
  return useQuery({
    queryKey: runtimeReadinessKeys.process,
    queryFn: getRuntimeEnvironmentReadiness,
    staleTime: 10_000,
    retry: false,
  });
}

/** Subscribe to the Run-owned safe Device Profile directory. */
export function useSafeDeviceProfiles() {
  return useQuery({
    queryKey: runtimeReadinessKeys.profiles,
    queryFn: getSafeDeviceProfiles,
    staleTime: 10_000,
    retry: false,
  });
}

/** Build exact readiness query options for launch and Builder consumers. */
export function exactRevisionReadinessQueryOptions(
  agentId: string,
  revisionId: string,
  profileId: string,
) {
  return queryOptions({
    queryKey: runtimeReadinessKeys.exact(agentId, revisionId, profileId),
    queryFn: () => getExactRevisionReadiness(agentId, revisionId, profileId),
    enabled: Boolean(agentId && revisionId && profileId),
    staleTime: 5_000,
    refetchInterval: 3_000,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    retry: false,
  });
}

/** Subscribe to exact immutable revision/Profile readiness. */
export function useExactRevisionReadiness(
  agentId: string,
  revisionId: string,
  profileId: string,
) {
  return useQuery(exactRevisionReadinessQueryOptions(agentId, revisionId, profileId));
}
