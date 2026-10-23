import { studioApiUrl, studioTextRequest } from "@/shared/api";

const OPAQUE_RUN_ID = /^run-[a-f0-9]{32}$/;
const OPAQUE_ARTIFACT_ID = /^artifact-[a-f0-9]{32}$/;

/** Require run-scoped opaque identities before constructing evidence URLs. */
function assertRunArtifactIdentity(runId: string, artifactId: string): void {
  if (!OPAQUE_RUN_ID.test(runId) || !OPAQUE_ARTIFACT_ID.test(artifactId)) {
    throw new Error("Run evidence requires opaque run and artifact identities");
  }
}

/** Build the opaque content URL for one run-scoped artifact. */
export function replayArtifactUrl(runId: string, artifactId: string): string {
  return studioApiUrl(
    `/api/studio/replays/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,
  );
}

/** Lazily load bounded text evidence from one immutable Replay artifact. */
export async function loadReplayArtifactText(
  runId: string,
  artifactId: string,
): Promise<string> {
  return studioTextRequest(
    `/api/studio/replays/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,
  );
}

/** Build one managed live Run artifact URL without accepting host paths. */
export function runArtifactUrl(runId: string, artifactId: string): string {
  assertRunArtifactIdentity(runId, artifactId);
  return studioApiUrl(
    `/api/studio/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,
  );
}

/** Lazily load bounded text evidence from the run-scoped content boundary. */
export async function loadRunArtifactText(
  runId: string,
  artifactId: string,
): Promise<string> {
  assertRunArtifactIdentity(runId, artifactId);
  return studioTextRequest(
    `/api/studio/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,
  );
}

/** Build the real versioned bundle download URL for one Replay. */
export function replayBundleUrl(runId: string): string {
  return studioApiUrl(`/api/studio/replays/${encodeURIComponent(runId)}/bundle`);
}
