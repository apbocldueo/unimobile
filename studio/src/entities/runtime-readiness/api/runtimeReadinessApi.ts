import { studioRequest } from "@/shared/api";
import {
  parseExactRevisionReadiness,
  parseRuntimeEnvironmentReadiness,
  parseSafeDeviceProfilePage,
  type ExactRevisionReadiness,
  type RuntimeEnvironmentReadiness,
  type SafeDeviceProfilePage,
} from "../model/runtimeReadiness.schema";

/** Read process-scoped static runtime configuration without secret values. */
export async function getRuntimeEnvironmentReadiness(): Promise<RuntimeEnvironmentReadiness> {
  return parseRuntimeEnvironmentReadiness(await studioRequest("/studio/runtime-readiness"));
}

/** Read exact revision/Profile static readiness without creating a Run. */
export async function getExactRevisionReadiness(
  agentId: string,
  revisionId: string,
  deviceProfileId: string,
): Promise<ExactRevisionReadiness> {
  const query = new URLSearchParams({ deviceProfileId });
  return parseExactRevisionReadiness(
    await studioRequest(
      `/studio/agents/${encodeURIComponent(agentId)}/revisions/${encodeURIComponent(revisionId)}/run-readiness?${query}`,
    ),
  );
}

/** Read the authoritative safe Profile list owned by ordinary Run launch. */
export async function getSafeDeviceProfiles(): Promise<SafeDeviceProfilePage> {
  return parseSafeDeviceProfilePage(await studioRequest("/studio/device-profiles"));
}
