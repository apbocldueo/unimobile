import { studioRequest } from "@/shared/api";
import {
  parseCreateStudioRunResponse,
  parseStudioRunEventPage,
  parseStudioRunResource,
  type CreateStudioRunInput,
  type CreateStudioRunResponse,
  type StudioRunEventPage,
  type StudioRunResource,
} from "../model/liveRun.schema";

/** Create or retrieve one idempotent ordinary Agent Run. */
export async function createStudioRun(
  input: CreateStudioRunInput,
): Promise<CreateStudioRunResponse> {
  return parseCreateStudioRunResponse(
    await studioRequest("/api/studio/runs", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  );
}

/** Load one authoritative Run resource. */
export async function getStudioRun(runId: string): Promise<StudioRunResource> {
  return parseStudioRunResource(
    await studioRequest(`/api/studio/runs/${encodeURIComponent(runId)}`),
  );
}

/** Request cooperative cancellation and return the current Run resource. */
export async function cancelStudioRun(runId: string): Promise<StudioRunResource> {
  return parseStudioRunResource(
    await studioRequest(`/api/studio/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      body: JSON.stringify({ schemaVersion: 1 }),
    }),
  );
}

/** Query one bounded journal page after an exclusive run-local cursor. */
export async function getStudioRunEvents(
  runId: string,
  after: number,
  limit = 100,
): Promise<StudioRunEventPage> {
  if (!Number.isInteger(after) || after < 0) throw new Error("after must be a non-negative integer");
  if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
    throw new Error("limit must be an integer from 1 through 500");
  }
  const query = new URLSearchParams({ after: String(after), limit: String(limit) });
  return parseStudioRunEventPage(
    await studioRequest(
      `/api/studio/runs/${encodeURIComponent(runId)}/events?${query.toString()}`,
    ),
  );
}
