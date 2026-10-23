import { isRecord, rejectUnknownKeys, requireNumber, requireString } from "@/shared/lib";
import type { EvidenceAvailabilityState } from "@/entities/run";
import { parseAvailabilityState } from "@/entities/run";

export type ReplayArtifact = {
  artifactId: string;
  kind: string;
  availability: EvidenceAvailabilityState;
  contentType: string;
  size: number;
  sha256: string | null;
  schemaVersion: string;
  provenance: string;
  hidden: boolean;
};

/** Parse one opaque Replay artifact descriptor without accepting paths. */
export function parseReplayArtifact(
  value: unknown,
  path = "artifact",
): ReplayArtifact {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "artifactId",
      "kind",
      "availability",
      "contentType",
      "size",
      "sha256",
      "schemaVersion",
      "provenance",
      "hidden",
    ],
    path,
  );
  return {
    artifactId: requireString(value.artifactId, `${path}.artifactId`),
    kind: requireString(value.kind, `${path}.kind`),
    availability: parseAvailabilityState(value.availability, `${path}.availability`),
    contentType: requireString(value.contentType, `${path}.contentType`),
    size: requireNumber(value.size, `${path}.size`),
    sha256: typeof value.sha256 === "string" ? value.sha256 : null,
    schemaVersion: requireString(value.schemaVersion, `${path}.schemaVersion`),
    provenance: typeof value.provenance === "string" ? value.provenance : "",
    hidden: value.hidden === true,
  };
}
