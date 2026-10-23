import { isRecord, rejectUnknownKeys, requireString } from "@/shared/lib";

export type RuntimeReadinessCategory = "revision" | "component" | "secret" | "profile" | "topology";

export type RuntimeReadinessDiagnostic = {
  code: string;
  category: RuntimeReadinessCategory;
  message: string;
  subjectIdentity: string | null;
  nodeId: string | null;
  remediationKey: string;
};

export type RuntimeProviderStatus = {
  identifier: string;
  category: string;
  available: boolean;
  errorType: string;
};

export type RuntimeSecretStatus = {
  secretRef: string;
  configured: boolean;
};

export type SafeDeviceProfile = {
  deviceProfileId: string;
  label: string;
  platform: "android" | "harmonyos";
  availability: "configured";
};

export type RuntimeEnvironmentReadiness = {
  schemaVersion: 1;
  ready: boolean;
  providers: RuntimeProviderStatus[];
  secrets: RuntimeSecretStatus[];
  deviceProfiles: SafeDeviceProfile[];
  diagnostics: RuntimeReadinessDiagnostic[];
};

export type ExactRevisionReadiness = {
  schemaVersion: 1;
  agentId: string;
  revisionId: string;
  canonicalHash: string | null;
  deviceProfileId: string;
  ready: boolean;
  diagnostics: RuntimeReadinessDiagnostic[];
};

export type SafeDeviceProfilePage = {
  schemaVersion: 1;
  items: SafeDeviceProfile[];
};

const CANONICAL_HASH = /^sha256:[0-9a-f]{64}$/;

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${path} must be a boolean`);
  return value;
}

function response(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error(`${path} must be a schemaVersion 1 object`);
  }
  return value;
}

function parseDiagnostic(value: unknown, path: string): RuntimeReadinessDiagnostic {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["code", "category", "message", "subjectIdentity", "nodeId", "remediationKey"],
    path,
  );
  const category = value.category;
  if (!["revision", "component", "secret", "profile", "topology"].includes(String(category))) {
    throw new Error(`${path}.category is unsupported`);
  }
  return {
    code: requireString(value.code, `${path}.code`),
    category: category as RuntimeReadinessCategory,
    message: requireString(value.message, `${path}.message`),
    subjectIdentity:
      value.subjectIdentity === null || value.subjectIdentity === undefined
        ? null
        : requireString(value.subjectIdentity, `${path}.subjectIdentity`),
    nodeId:
      value.nodeId === null || value.nodeId === undefined
        ? null
        : requireString(value.nodeId, `${path}.nodeId`),
    remediationKey: requireString(value.remediationKey, `${path}.remediationKey`),
  };
}

function parseProfile(value: unknown, path: string): SafeDeviceProfile {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["deviceProfileId", "label", "platform", "availability"], path);
  if (value.platform !== "android" && value.platform !== "harmonyos") {
    throw new Error(`${path}.platform is unsupported`);
  }
  if (value.availability !== "configured") {
    throw new Error(`${path}.availability is unsupported`);
  }
  return {
    deviceProfileId: requireString(value.deviceProfileId, `${path}.deviceProfileId`),
    label: requireString(value.label, `${path}.label`),
    platform: value.platform,
    availability: "configured",
  };
}

/** Parse the safe process-level runtime configuration projection. */
export function parseRuntimeEnvironmentReadiness(value: unknown): RuntimeEnvironmentReadiness {
  const raw = response(value, "runtimeReadiness");
  rejectUnknownKeys(
    raw,
    ["schemaVersion", "ready", "providers", "secrets", "deviceProfiles", "diagnostics"],
    "runtimeReadiness",
  );
  if (!Array.isArray(raw.providers) || !Array.isArray(raw.secrets)
    || !Array.isArray(raw.deviceProfiles) || !Array.isArray(raw.diagnostics)) {
    throw new Error("runtimeReadiness collections are invalid");
  }
  return {
    schemaVersion: 1,
    ready: requireBoolean(raw.ready, "runtimeReadiness.ready"),
    providers: raw.providers.map((item, index) => {
      const path = `runtimeReadiness.providers[${index}]`;
      if (!isRecord(item)) throw new Error(`${path} must be an object`);
      rejectUnknownKeys(item, ["identifier", "category", "available", "errorType"], path);
      return {
        identifier: requireString(item.identifier, `${path}.identifier`),
        category: requireString(item.category, `${path}.category`),
        available: requireBoolean(item.available, `${path}.available`),
        errorType: typeof item.errorType === "string" ? item.errorType : "",
      };
    }),
    secrets: raw.secrets.map((item, index) => {
      const path = `runtimeReadiness.secrets[${index}]`;
      if (!isRecord(item)) throw new Error(`${path} must be an object`);
      rejectUnknownKeys(item, ["secretRef", "configured"], path);
      return {
        secretRef: requireString(item.secretRef, `${path}.secretRef`),
        configured: requireBoolean(item.configured, `${path}.configured`),
      };
    }),
    deviceProfiles: raw.deviceProfiles.map((item, index) =>
      parseProfile(item, `runtimeReadiness.deviceProfiles[${index}]`),
    ),
    diagnostics: raw.diagnostics.map((item, index) =>
      parseDiagnostic(item, `runtimeReadiness.diagnostics[${index}]`),
    ),
  };
}

/** Parse static readiness for one exact immutable revision and selected Profile. */
export function parseExactRevisionReadiness(value: unknown): ExactRevisionReadiness {
  const raw = response(value, "exactReadiness");
  rejectUnknownKeys(
    raw,
    ["schemaVersion", "agentId", "revisionId", "canonicalHash", "deviceProfileId", "ready", "diagnostics"],
    "exactReadiness",
  );
  if (!Array.isArray(raw.diagnostics)) throw new Error("exactReadiness.diagnostics must be an array");
  const canonicalHash = raw.canonicalHash === null || raw.canonicalHash === undefined
    ? null
    : requireString(raw.canonicalHash, "exactReadiness.canonicalHash");
  if (canonicalHash !== null && !CANONICAL_HASH.test(canonicalHash)) {
    throw new Error("exactReadiness.canonicalHash is invalid");
  }
  return {
    schemaVersion: 1,
    agentId: requireString(raw.agentId, "exactReadiness.agentId"),
    revisionId: requireString(raw.revisionId, "exactReadiness.revisionId"),
    canonicalHash,
    deviceProfileId: requireString(raw.deviceProfileId, "exactReadiness.deviceProfileId"),
    ready: requireBoolean(raw.ready, "exactReadiness.ready"),
    diagnostics: raw.diagnostics.map((item, index) =>
      parseDiagnostic(item, `exactReadiness.diagnostics[${index}]`),
    ),
  };
}

/** Parse the Run-owned safe Device Profile directory. */
export function parseSafeDeviceProfilePage(value: unknown): SafeDeviceProfilePage {
  const raw = response(value, "deviceProfiles");
  rejectUnknownKeys(raw, ["schemaVersion", "items"], "deviceProfiles");
  if (!Array.isArray(raw.items)) throw new Error("deviceProfiles.items must be an array");
  return {
    schemaVersion: 1,
    items: raw.items.map((item, index) => parseProfile(item, `deviceProfiles.items[${index}]`)),
  };
}
