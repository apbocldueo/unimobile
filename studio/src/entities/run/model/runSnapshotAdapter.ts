import type { AgentRevision } from "@/entities/agent-revision";
import type { StudioRunResource } from "./liveRun.schema";
import { parseRunSnapshot, type RunSnapshot } from "./run.schema";

/** Validate and adapt an exact immutable revision before any Run exists.
 *
 * Args:
 *   revision: Persisted Agent revision selected by the launch route.
 *
 * Returns:
 *   A read-only graph snapshot suitable for a not-started workbench.
 *
 * Raises:
 *   Error: The revision is invalid or lacks a compiled AgentGraph/canonical hash.
 */
export function adaptRevisionToLaunchSnapshot(revision: AgentRevision): RunSnapshot {
  if (revision.compileSnapshot.status !== "valid") {
    throw new Error("Launch revision compile status is invalid");
  }
  if (!revision.compileSnapshot.agentGraph) {
    throw new Error("Launch revision has no compiled AgentGraph");
  }
  if (!revision.compileSnapshot.canonicalHash) {
    throw new Error("Launch revision has no canonical identity");
  }
  return parseRunSnapshot({
    agentId: revision.agentId,
    revisionId: revision.revisionId,
    contractVersion: revision.document.contractVersion,
    canonicalHash: revision.compileSnapshot.canonicalHash,
    graphStatus: "available",
    agentGraph: revision.compileSnapshot.agentGraph,
    presentation: revision.document.presentation,
    sourceMap: revision.compileSnapshot.sourceMap,
    authoringPolicy: revision.compileSnapshot.authoringPolicy,
    loweringProfile: revision.compileSnapshot.loweringProfile,
    capabilityHash: revision.compileSnapshot.capabilityHash,
    capabilityDocument: revision.document,
    projectionMap: revision.compileSnapshot.projectionMap,
    providerIdentities: [],
  });
}

/** Verify and adapt the exact immutable authoring revision used by one Run. */
export function adaptRevisionToRunSnapshot(
  revision: AgentRevision,
  run: StudioRunResource,
): RunSnapshot {
  if (revision.agentId !== run.agentId) {
    throw new Error("Run Agent identity does not match the loaded revision");
  }
  if (revision.revisionId !== run.revisionId) {
    throw new Error("Run revision identity does not match the loaded revision");
  }
  if (revision.compileSnapshot.status !== "valid") {
    throw new Error("Run revision compile status is invalid");
  }
  if (!revision.compileSnapshot.agentGraph) {
    throw new Error("Run revision has no compiled AgentGraph");
  }
  if (revision.compileSnapshot.canonicalHash !== run.canonicalHash) {
    throw new Error("Run canonical hash does not match the loaded revision");
  }
  return parseRunSnapshot({
    agentId: revision.agentId,
    revisionId: revision.revisionId,
    contractVersion: revision.document.contractVersion,
    canonicalHash: revision.compileSnapshot.canonicalHash,
    graphStatus: "available",
    agentGraph: revision.compileSnapshot.agentGraph,
    presentation: revision.document.presentation,
    sourceMap: revision.compileSnapshot.sourceMap,
    authoringPolicy: revision.compileSnapshot.authoringPolicy,
    loweringProfile: revision.compileSnapshot.loweringProfile,
    capabilityHash: revision.compileSnapshot.capabilityHash,
    capabilityDocument: revision.document,
    projectionMap: revision.compileSnapshot.projectionMap,
    providerIdentities: [],
  });
}
