import {
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
} from "@/shared/lib";

export type BenchmarkSourceKind = "package" | "catalog" | "installed";
export type BenchmarkAvailability = "available" | "invalid";
export type BenchmarkPlatform = "android" | "harmonyos";

export type BenchmarkDiagnostic = {
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
  source: string;
  path: Array<string | number>;
  taskId: string | null;
};

export type BenchmarkSplitSummary = {
  name: string;
  taskCount: number | null;
};

export type BenchmarkCatalogEntry = {
  catalogEntryId: string;
  packageIdentity: string;
  title: string;
  version: string;
  sourceKind: BenchmarkSourceKind;
  platforms: BenchmarkPlatform[];
  splits: BenchmarkSplitSummary[];
  availability: BenchmarkAvailability;
  warnings: BenchmarkDiagnostic[];
};

export type BenchmarkCatalogPage = {
  schemaVersion: 1;
  items: BenchmarkCatalogEntry[];
  nextCursor: string | null;
};

export type BenchmarkRequirement = {
  id: string;
  kind: "app" | "plugin";
  platform: string;
  version: string;
  optional: boolean;
  requiresLogin: boolean;
};

export type BenchmarkResource = {
  id: string;
  kind: string;
  mediaType: string;
  sha256: string;
  size: number;
};

export type BenchmarkDetail = {
  schemaVersion: 1;
  catalogEntryId: string;
  packageIdentity: string;
  packageContentIdentity: string | null;
  title: string;
  version: string;
  sourceKind: BenchmarkSourceKind;
  availability: BenchmarkAvailability;
  platforms: BenchmarkPlatform[];
  splits: BenchmarkSplitSummary[];
  requirements: BenchmarkRequirement[];
  resources: BenchmarkResource[];
  defaultProtocol: Record<string, unknown> | null;
  diagnostics: BenchmarkDiagnostic[];
};

export type BenchmarkTask = {
  taskId: string;
  split: string;
  instruction: string;
  app: string | null;
  taskType: "static" | "dynamic";
  requiresLogin: boolean | null;
  maxSteps: number | null;
  initializerCount: number;
  evaluatorKind: string;
};

export type BenchmarkTaskPage = {
  schemaVersion: 1;
  catalogEntryId: string;
  split: string;
  items: BenchmarkTask[];
  nextCursor: string | null;
};

export type BenchmarkValidationResult = {
  schemaVersion: 1;
  catalogEntryId: string;
  valid: boolean;
  identities: {
    package: string | null;
    packageContent: string | null;
    benchmarkPlan: string | null;
    experimentProtocol: string | null;
  };
  diagnostics: BenchmarkDiagnostic[];
};

export type DeviceProfile = {
  deviceProfileId: string;
  label: string;
  platform: BenchmarkPlatform;
  availability: "configured";
};

export type DeviceProfilePage = {
  schemaVersion: 1;
  items: DeviceProfile[];
};

/** Require a strict version-one response object. */
function responseObject(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error(`${path} must be a schemaVersion 1 object`);
  }
  return value;
}

/** Parse a nullable string without accepting another primitive. */
function nullableString(value: unknown, path: string): string | null {
  if (value === null || value === undefined) return null;
  return requireString(value, path);
}

/** Parse one supported platform value. */
function platform(value: unknown, path: string): BenchmarkPlatform {
  if (value !== "android" && value !== "harmonyos") {
    throw new Error(`${path} has an unsupported platform`);
  }
  return value;
}

/** Parse one safe backend diagnostic. */
export function parseBenchmarkDiagnostic(
  value: unknown,
  path = "diagnostic",
): BenchmarkDiagnostic {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["code", "message", "severity", "source", "path", "taskId"],
    path,
  );
  if (
    value.severity !== "error"
    && value.severity !== "warning"
    && value.severity !== "info"
  ) {
    throw new Error(`${path}.severity is unsupported`);
  }
  if (!Array.isArray(value.path)) throw new Error(`${path}.path must be an array`);
  return {
    code: requireString(value.code, `${path}.code`),
    message: requireString(value.message, `${path}.message`),
    severity: value.severity,
    source: typeof value.source === "string" ? value.source : "",
    path: value.path.map((item, index) => {
      if (typeof item !== "string" && typeof item !== "number") {
        throw new Error(`${path}.path[${index}] is invalid`);
      }
      return item;
    }),
    taskId: nullableString(value.taskId, `${path}.taskId`),
  };
}

/** Parse one split summary. */
function parseSplit(value: unknown, path: string): BenchmarkSplitSummary {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["name", "taskCount"], path);
  return {
    name: requireString(value.name, `${path}.name`),
    taskCount:
      value.taskCount === null || value.taskCount === undefined
        ? null
        : requireNumber(value.taskCount, `${path}.taskCount`),
  };
}

/** Parse one Catalog list item. */
export function parseBenchmarkCatalogEntry(
  value: unknown,
  path = "entry",
): BenchmarkCatalogEntry {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "catalogEntryId",
      "packageIdentity",
      "title",
      "version",
      "sourceKind",
      "platforms",
      "splits",
      "availability",
      "warnings",
    ],
    path,
  );
  if (
    value.sourceKind !== "package"
    && value.sourceKind !== "catalog"
    && value.sourceKind !== "installed"
  ) {
    throw new Error(`${path}.sourceKind is unsupported`);
  }
  if (value.availability !== "available" && value.availability !== "invalid") {
    throw new Error(`${path}.availability is unsupported`);
  }
  if (!Array.isArray(value.platforms) || !Array.isArray(value.splits)) {
    throw new Error(`${path} platforms and splits must be arrays`);
  }
  const warnings = value.warnings ?? [];
  if (!Array.isArray(warnings)) throw new Error(`${path}.warnings must be an array`);
  return {
    catalogEntryId: requireString(value.catalogEntryId, `${path}.catalogEntryId`),
    packageIdentity: requireString(value.packageIdentity, `${path}.packageIdentity`),
    title: requireString(value.title, `${path}.title`),
    version: requireString(value.version, `${path}.version`),
    sourceKind: value.sourceKind,
    platforms: value.platforms.map((item, index) =>
      platform(item, `${path}.platforms[${index}]`),
    ),
    splits: value.splits.map((item, index) =>
      parseSplit(item, `${path}.splits[${index}]`),
    ),
    availability: value.availability,
    warnings: warnings.map((item, index) =>
      parseBenchmarkDiagnostic(item, `${path}.warnings[${index}]`),
    ),
  };
}

/** Parse a strict Benchmark Catalog page. */
export function parseBenchmarkCatalogPage(value: unknown): BenchmarkCatalogPage {
  const record = responseObject(value, "catalogPage");
  rejectUnknownKeys(record, ["schemaVersion", "items", "nextCursor"], "catalogPage");
  if (!Array.isArray(record.items)) throw new Error("catalogPage.items must be an array");
  return {
    schemaVersion: 1,
    items: record.items.map((item, index) =>
      parseBenchmarkCatalogEntry(item, `catalogPage.items[${index}]`),
    ),
    nextCursor: nullableString(record.nextCursor, "catalogPage.nextCursor"),
  };
}

/** Parse one safe requirement projection. */
function parseRequirement(value: unknown, path: string): BenchmarkRequirement {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["id", "kind", "platform", "version", "optional", "requiresLogin"],
    path,
  );
  if (value.kind !== "app" && value.kind !== "plugin") {
    throw new Error(`${path}.kind is unsupported`);
  }
  if (typeof value.optional !== "boolean" || typeof value.requiresLogin !== "boolean") {
    throw new Error(`${path} boolean flags are invalid`);
  }
  return {
    id: requireString(value.id, `${path}.id`),
    kind: value.kind,
    platform: typeof value.platform === "string" ? value.platform : "",
    version: typeof value.version === "string" ? value.version : "",
    optional: value.optional,
    requiresLogin: value.requiresLogin,
  };
}

/** Parse one content-addressed resource projection. */
function parseResource(value: unknown, path: string): BenchmarkResource {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["id", "kind", "mediaType", "sha256", "size"], path);
  return {
    id: requireString(value.id, `${path}.id`),
    kind: requireString(value.kind, `${path}.kind`),
    mediaType: requireString(value.mediaType, `${path}.mediaType`),
    sha256: requireString(value.sha256, `${path}.sha256`),
    size: requireNumber(value.size, `${path}.size`),
  };
}

/** Parse a strict Benchmark detail response. */
export function parseBenchmarkDetail(value: unknown): BenchmarkDetail {
  const record = responseObject(value, "benchmarkDetail");
  rejectUnknownKeys(
    record,
    [
      "schemaVersion",
      "catalogEntryId",
      "packageIdentity",
      "packageContentIdentity",
      "title",
      "version",
      "sourceKind",
      "availability",
      "platforms",
      "splits",
      "requirements",
      "resources",
      "defaultProtocol",
      "diagnostics",
    ],
    "benchmarkDetail",
  );
  const entry = parseBenchmarkCatalogEntry({
    catalogEntryId: record.catalogEntryId,
    packageIdentity: record.packageIdentity,
    title: record.title,
    version: record.version,
    sourceKind: record.sourceKind,
    platforms: record.platforms,
    splits: record.splits,
    availability: record.availability,
    warnings: record.diagnostics ?? [],
  });
  if (
    !Array.isArray(record.requirements)
    || !Array.isArray(record.resources)
    || !Array.isArray(record.diagnostics)
  ) {
    throw new Error("benchmarkDetail collections must be arrays");
  }
  if (
    record.defaultProtocol !== null
    && record.defaultProtocol !== undefined
    && !isRecord(record.defaultProtocol)
  ) {
    throw new Error("benchmarkDetail.defaultProtocol must be an object or null");
  }
  return {
    schemaVersion: 1,
    catalogEntryId: entry.catalogEntryId,
    packageIdentity: entry.packageIdentity,
    packageContentIdentity: nullableString(
      record.packageContentIdentity,
      "benchmarkDetail.packageContentIdentity",
    ),
    title: entry.title,
    version: entry.version,
    sourceKind: entry.sourceKind,
    availability: entry.availability,
    platforms: entry.platforms,
    splits: entry.splits,
    requirements: record.requirements.map((item, index) =>
      parseRequirement(item, `benchmarkDetail.requirements[${index}]`),
    ),
    resources: record.resources.map((item, index) =>
      parseResource(item, `benchmarkDetail.resources[${index}]`),
    ),
    defaultProtocol: (record.defaultProtocol as Record<string, unknown> | null) ?? null,
    diagnostics: record.diagnostics.map((item, index) =>
      parseBenchmarkDiagnostic(item, `benchmarkDetail.diagnostics[${index}]`),
    ),
  };
}

/** Parse one safe task template. */
export function parseBenchmarkTask(value: unknown, path = "task"): BenchmarkTask {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "taskId",
      "split",
      "instruction",
      "app",
      "taskType",
      "requiresLogin",
      "maxSteps",
      "initializerCount",
      "evaluatorKind",
    ],
    path,
  );
  if (value.taskType !== "static" && value.taskType !== "dynamic") {
    throw new Error(`${path}.taskType is unsupported`);
  }
  if (
    value.requiresLogin !== null
    && value.requiresLogin !== undefined
    && typeof value.requiresLogin !== "boolean"
  ) {
    throw new Error(`${path}.requiresLogin is invalid`);
  }
  return {
    taskId: requireString(value.taskId, `${path}.taskId`),
    split: requireString(value.split, `${path}.split`),
    instruction: requireString(value.instruction, `${path}.instruction`),
    app: nullableString(value.app, `${path}.app`),
    taskType: value.taskType,
    requiresLogin: value.requiresLogin ?? null,
    maxSteps:
      value.maxSteps === null || value.maxSteps === undefined
        ? null
        : requireNumber(value.maxSteps, `${path}.maxSteps`),
    initializerCount: requireNumber(value.initializerCount, `${path}.initializerCount`),
    evaluatorKind: requireString(value.evaluatorKind, `${path}.evaluatorKind`),
  };
}

/** Parse a strict Benchmark task page. */
export function parseBenchmarkTaskPage(value: unknown): BenchmarkTaskPage {
  const record = responseObject(value, "taskPage");
  rejectUnknownKeys(
    record,
    ["schemaVersion", "catalogEntryId", "split", "items", "nextCursor"],
    "taskPage",
  );
  if (!Array.isArray(record.items)) throw new Error("taskPage.items must be an array");
  return {
    schemaVersion: 1,
    catalogEntryId: requireString(record.catalogEntryId, "taskPage.catalogEntryId"),
    split: requireString(record.split, "taskPage.split"),
    items: record.items.map((item, index) =>
      parseBenchmarkTask(item, `taskPage.items[${index}]`),
    ),
    nextCursor: nullableString(record.nextCursor, "taskPage.nextCursor"),
  };
}

/** Parse an explicit full-definition validation result. */
export function parseBenchmarkValidationResult(
  value: unknown,
): BenchmarkValidationResult {
  const record = responseObject(value, "validation");
  rejectUnknownKeys(
    record,
    ["schemaVersion", "catalogEntryId", "valid", "identities", "diagnostics"],
    "validation",
  );
  if (
    typeof record.valid !== "boolean"
    || !isRecord(record.identities)
    || !Array.isArray(record.diagnostics)
  ) {
    throw new Error("validation response shape is invalid");
  }
  rejectUnknownKeys(
    record.identities,
    ["package", "packageContent", "benchmarkPlan", "experimentProtocol"],
    "validation.identities",
  );
  return {
    schemaVersion: 1,
    catalogEntryId: requireString(record.catalogEntryId, "validation.catalogEntryId"),
    valid: record.valid,
    identities: {
      package: nullableString(record.identities.package, "validation.identities.package"),
      packageContent: nullableString(
        record.identities.packageContent,
        "validation.identities.packageContent",
      ),
      benchmarkPlan: nullableString(
        record.identities.benchmarkPlan,
        "validation.identities.benchmarkPlan",
      ),
      experimentProtocol: nullableString(
        record.identities.experimentProtocol,
        "validation.identities.experimentProtocol",
      ),
    },
    diagnostics: record.diagnostics.map((item, index) =>
      parseBenchmarkDiagnostic(item, `validation.diagnostics[${index}]`),
    ),
  };
}

/** Parse the safe configured device-profile directory. */
export function parseDeviceProfilePage(value: unknown): DeviceProfilePage {
  const record = responseObject(value, "deviceProfiles");
  rejectUnknownKeys(record, ["schemaVersion", "items"], "deviceProfiles");
  if (!Array.isArray(record.items)) throw new Error("deviceProfiles.items must be an array");
  return {
    schemaVersion: 1,
    items: record.items.map((item, index) => {
      const path = `deviceProfiles.items[${index}]`;
      if (!isRecord(item)) throw new Error(`${path} must be an object`);
      rejectUnknownKeys(
        item,
        ["deviceProfileId", "label", "platform", "availability"],
        path,
      );
      if (item.availability !== "configured") {
        throw new Error(`${path}.availability is unsupported`);
      }
      return {
        deviceProfileId: requireString(item.deviceProfileId, `${path}.deviceProfileId`),
        label: requireString(item.label, `${path}.label`),
        platform: platform(item.platform, `${path}.platform`),
        availability: "configured",
      };
    }),
  };
}
