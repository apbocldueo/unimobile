import type { ExecutionEvidenceOrigin } from "./evidenceOrigin.schema";

export type EvidenceOriginPresentationKind =
  | "fresh-real-source"
  | "historical-real-source"
  | "fake-fixture"
  | "unverified";

export type EvidenceOriginPresentation = {
  kind: EvidenceOriginPresentationKind;
  label: string;
  description: string;
  origin: ExecutionEvidenceOrigin;
};

/** Classify authoritative evidence facts for consistent cross-surface copy.
 *
 * The classifier is presentation-only: it never upgrades or repairs the
 * already strictly parsed acquisition, environment, profile, device checks,
 * or real-device-evidence flag.
 */
export function classifyEvidenceOrigin(
  origin: ExecutionEvidenceOrigin,
): EvidenceOriginPresentation {
  if (
    origin.acquisition === "fresh_execution"
    && origin.environment === "real_android"
    && origin.realDeviceEvidence
  ) {
    return {
      kind: "fresh-real-source",
      label: "Fresh real-Android source",
      description:
        "This TaskResult is fresh source evidence from the declared real-Android environment.",
      origin,
    };
  }
  if (
    origin.acquisition === "replay_projection"
    && origin.environment === "real_android"
    && !origin.realDeviceEvidence
  ) {
    return {
      kind: "historical-real-source",
      label: "Historical projection of a real-Android source",
      description:
        "The source environment was real Android, but this resource is a read-only historical projection, not a new fresh-device execution.",
      origin,
    };
  }
  if (
    origin.acquisition === "contract_fixture"
    && origin.environment === "fake_device"
    && !origin.realDeviceEvidence
  ) {
    return {
      kind: "fake-fixture",
      label: "Supporting fake-device fixture",
      description:
        "This evidence comes from a contract fixture on a fake device and is not real-device evidence.",
      origin,
    };
  }
  return {
    kind: "unverified",
    label: "Unverified evidence origin",
    description:
      "These source facts do not establish fresh real-Android execution; no URL, title, profile, screenshot, or artifact can upgrade them.",
    origin,
  };
}
