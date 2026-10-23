import { isRecord, rejectUnknownKeys, requireString } from "@/shared/lib";

export type EvidenceAcquisition =
  | "fresh_execution"
  | "replay_projection"
  | "imported_excerpt"
  | "contract_fixture";

export type EvidenceEnvironment =
  | "real_android"
  | "fake_device"
  | "unverified";

export type DeviceContextCheck = {
  name: "platform" | "locale" | "orientation" | "apps";
  passed: boolean;
  observed: string;
};

export type ExecutionEvidenceOrigin = {
  schemaVersion: 1;
  acquisition: EvidenceAcquisition;
  environment: EvidenceEnvironment;
  deviceProfileId: string | null;
  deviceChecks: DeviceContextCheck[];
  realDeviceEvidence: boolean;
};

const ACQUISITIONS = new Set<EvidenceAcquisition>([
  "fresh_execution",
  "replay_projection",
  "imported_excerpt",
  "contract_fixture",
]);
const ENVIRONMENTS = new Set<EvidenceEnvironment>([
  "real_android",
  "fake_device",
  "unverified",
]);
const CHECK_NAMES = new Set<DeviceContextCheck["name"]>([
  "platform",
  "locale",
  "orientation",
  "apps",
]);

/** Build the conservative typed origin used for historical responses. */
export function historicalEvidenceOrigin(
  provenance = "",
): ExecutionEvidenceOrigin {
  if (provenance === "fake_contract_fixture") {
    return {
      schemaVersion: 1,
      acquisition: "contract_fixture",
      environment: "fake_device",
      deviceProfileId: null,
      deviceChecks: [],
      realDeviceEvidence: false,
    };
  }
  if (provenance === "real_android_excerpt") {
    return {
      schemaVersion: 1,
      acquisition: "imported_excerpt",
      environment: "real_android",
      deviceProfileId: null,
      deviceChecks: [],
      realDeviceEvidence: false,
    };
  }
  return {
    schemaVersion: 1,
    acquisition: provenance.startsWith("native_")
      ? "replay_projection"
      : provenance
        ? "imported_excerpt"
        : "fresh_execution",
    environment: "unverified",
    deviceProfileId: null,
    deviceChecks: [],
    realDeviceEvidence: false,
  };
}

/** Strictly parse bounded public execution-evidence provenance. */
export function parseExecutionEvidenceOrigin(
  value: unknown,
  path = "evidenceOrigin",
  fallbackProvenance = "",
): ExecutionEvidenceOrigin {
  if (value === null || value === undefined) {
    return historicalEvidenceOrigin(fallbackProvenance);
  }
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "acquisition",
      "environment",
      "deviceProfileId",
      "deviceChecks",
      "realDeviceEvidence",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const acquisition = requireString(value.acquisition, `${path}.acquisition`);
  if (!ACQUISITIONS.has(acquisition as EvidenceAcquisition)) {
    throw new Error(`${path}.acquisition is unsupported`);
  }
  const environment = requireString(value.environment, `${path}.environment`);
  if (!ENVIRONMENTS.has(environment as EvidenceEnvironment)) {
    throw new Error(`${path}.environment is unsupported`);
  }
  if (!Array.isArray(value.deviceChecks) || value.deviceChecks.length > 4) {
    throw new Error(`${path}.deviceChecks must be a bounded array`);
  }
  const deviceChecks = value.deviceChecks.map((item, index): DeviceContextCheck => {
    const itemPath = `${path}.deviceChecks[${index}]`;
    if (!isRecord(item)) throw new Error(`${itemPath} must be an object`);
    rejectUnknownKeys(item, ["name", "passed", "observed"], itemPath);
    const name = requireString(item.name, `${itemPath}.name`);
    if (!CHECK_NAMES.has(name as DeviceContextCheck["name"])) {
      throw new Error(`${itemPath}.name is unsupported`);
    }
    if (typeof item.passed !== "boolean") {
      throw new Error(`${itemPath}.passed must be a boolean`);
    }
    const observed = requireString(item.observed, `${itemPath}.observed`);
    if (observed.length > 160 || observed.includes("\n") || observed.includes("\r")) {
      throw new Error(`${itemPath}.observed is unsafe`);
    }
    return {
      name: name as DeviceContextCheck["name"],
      passed: item.passed,
      observed,
    };
  });
  if (new Set(deviceChecks.map((item) => item.name)).size !== deviceChecks.length) {
    throw new Error(`${path}.deviceChecks contains duplicate names`);
  }
  const deviceProfileId =
    value.deviceProfileId === null || value.deviceProfileId === undefined
      ? null
      : requireString(value.deviceProfileId, `${path}.deviceProfileId`);
  if (deviceProfileId !== null && !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/.test(deviceProfileId)) {
    throw new Error(`${path}.deviceProfileId is invalid`);
  }
  if (typeof value.realDeviceEvidence !== "boolean") {
    throw new Error(`${path}.realDeviceEvidence must be a boolean`);
  }
  const expectedRealEvidence =
    acquisition === "fresh_execution" && environment === "real_android";
  if (value.realDeviceEvidence !== expectedRealEvidence) {
    throw new Error(`${path}.realDeviceEvidence conflicts with source facts`);
  }
  return {
    schemaVersion: 1,
    acquisition: acquisition as EvidenceAcquisition,
    environment: environment as EvidenceEnvironment,
    deviceProfileId,
    deviceChecks,
    realDeviceEvidence: value.realDeviceEvidence,
  };
}
