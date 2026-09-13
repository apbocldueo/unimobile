import {
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
} from "@/shared/lib";
import {
  parseBenchmarkDiagnostic,
  type BenchmarkDiagnostic,
  type BenchmarkPlatform,
} from "@/entities/benchmark-catalog";

export type ProtocolAppRequirement = {
  id: string;
  platform: BenchmarkPlatform;
  packageId?: string;
  version?: string;
  requiresLogin: boolean;
};

export type ProtocolFailureRule = {
  outcome: "invalidate" | "fail" | "evaluate_if_possible" | "preserve";
  continueSuite: boolean;
  preserveEvidence: boolean;
};

export type ExperimentProtocol = {
  schemaVersion: "1.0";
  seed: number;
  repeats: number;
  taskOrder: { strategy: "fixed" | "seeded" };
  taskMaterialization: {
    reuseAcrossAgents: boolean;
    strictFairness: boolean;
  };
  device: {
    platform: BenchmarkPlatform;
    locale: string;
    orientation: "portrait" | "landscape" | "any";
    versionPolicy: "exact" | "compatible" | "any";
    osVersion?: string;
  };
  apps: ProtocolAppRequirement[];
  budget: {
    maxInteractions: number;
    maxActivations: number;
    timeoutSeconds: number;
    tokenLimit?: number;
    requireObservableTokens: boolean;
  };
  isolation: {
    reset: "before_each_agent" | "before_each_task" | "once";
    cleanup: "after_each_run" | "after_each_task" | "once";
    requireVerifiedReset: boolean;
  };
  failure: {
    initializer: ProtocolFailureRule;
    agent: ProtocolFailureRule;
    evaluator: ProtocolFailureRule;
    cleanup: ProtocolFailureRule;
  };
};

export type ExperimentPreviewRequest = {
  schemaVersion: 1;
  agentRevisions: Array<{ agentId: string; revisionId: string }>;
  benchmark: {
    catalogEntryId: string;
    split: string;
    taskIds: string[];
  };
  protocol: ExperimentProtocol;
  deviceProfileId: string;
};

export type ExperimentPreview = {
  schemaVersion: 1;
  previewOnly: true;
  previewFingerprint: string;
  identities: {
    package: string;
    packageContent: string;
    benchmarkPlan: string;
    experimentProtocol: string;
  };
  agentRevisions: Array<{
    agentId: string;
    revisionId: string;
    agentGraph: string;
  }>;
  normalizedProtocol: ExperimentProtocol;
  deviceProfileId: string;
  executionLimits: {
    maxAgents: 1;
    maxSelectedTasks: 1;
    maxRepeats: 1;
    multiAgentComparison: false;
  };
  schedule: Array<{
    plannedEntryId: string;
    agentId: string;
    revisionId: string;
    taskId: string;
    repeat: number;
    order: number;
    derivedSeed: number;
    taskInstance: {
      availability: "pending_materialization" | "template_only";
      identity: null;
      parameters: null;
    };
  }>;
  diagnostics: BenchmarkDiagnostic[];
};

/** Build the explicit Stage 5.1 research defaults for a selected platform. */
export function defaultExperimentProtocol(
  platform: BenchmarkPlatform = "android",
): ExperimentProtocol {
  return {
    schemaVersion: "1.0",
    seed: 42,
    repeats: 1,
    taskOrder: { strategy: "fixed" },
    taskMaterialization: {
      reuseAcrossAgents: true,
      strictFairness: false,
    },
    device: {
      platform,
      locale: "en-US",
      orientation: "portrait",
      versionPolicy: "compatible",
    },
    apps: [],
    budget: {
      maxInteractions: 15,
      maxActivations: 200,
      timeoutSeconds: 600,
      requireObservableTokens: false,
    },
    isolation: {
      reset: "before_each_agent",
      cleanup: "after_each_run",
      requireVerifiedReset: true,
    },
    failure: {
      initializer: {
        outcome: "invalidate",
        continueSuite: true,
        preserveEvidence: true,
      },
      agent: {
        outcome: "evaluate_if_possible",
        continueSuite: true,
        preserveEvidence: true,
      },
      evaluator: {
        outcome: "invalidate",
        continueSuite: true,
        preserveEvidence: true,
      },
      cleanup: {
        outcome: "invalidate",
        continueSuite: true,
        preserveEvidence: true,
      },
    },
  };
}

/** Require one boolean protocol field. */
function booleanField(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${path} must be a boolean`);
  return value;
}

/** Require one protocol enum member. */
function enumField<T extends string>(
  value: unknown,
  allowed: readonly T[],
  path: string,
): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    throw new Error(`${path} is unsupported`);
  }
  return value as T;
}

/** Parse one strict stage failure rule. */
function parseFailureRule(value: unknown, path: string): ProtocolFailureRule {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["outcome", "continueSuite", "preserveEvidence"], path);
  return {
    outcome: enumField(
      value.outcome,
      ["invalidate", "fail", "evaluate_if_possible", "preserve"] as const,
      `${path}.outcome`,
    ),
    continueSuite: booleanField(value.continueSuite, `${path}.continueSuite`),
    preserveEvidence: booleanField(
      value.preserveEvidence,
      `${path}.preserveEvidence`,
    ),
  };
}

/** Parse a formal ExperimentProtocol without competing browser defaults. */
export function parseExperimentProtocol(
  value: unknown,
  path = "protocol",
): ExperimentProtocol {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "seed",
      "repeats",
      "taskOrder",
      "taskMaterialization",
      "device",
      "apps",
      "budget",
      "isolation",
      "failure",
    ],
    path,
  );
  if (
    value.schemaVersion !== "1.0"
    || !isRecord(value.taskOrder)
    || !isRecord(value.taskMaterialization)
    || !isRecord(value.device)
    || !Array.isArray(value.apps)
    || !isRecord(value.budget)
    || !isRecord(value.isolation)
    || !isRecord(value.failure)
  ) {
    throw new Error(`${path} has an invalid formal shape`);
  }
  rejectUnknownKeys(value.taskOrder, ["strategy"], `${path}.taskOrder`);
  rejectUnknownKeys(
    value.taskMaterialization,
    ["reuseAcrossAgents", "strictFairness"],
    `${path}.taskMaterialization`,
  );
  rejectUnknownKeys(
    value.device,
    ["platform", "locale", "orientation", "versionPolicy", "osVersion"],
    `${path}.device`,
  );
  rejectUnknownKeys(
    value.budget,
    [
      "maxInteractions",
      "maxActivations",
      "timeoutSeconds",
      "tokenLimit",
      "requireObservableTokens",
    ],
    `${path}.budget`,
  );
  rejectUnknownKeys(
    value.isolation,
    ["reset", "cleanup", "requireVerifiedReset"],
    `${path}.isolation`,
  );
  rejectUnknownKeys(
    value.failure,
    ["initializer", "agent", "evaluator", "cleanup"],
    `${path}.failure`,
  );
  const apps = value.apps.map((item, index): ProtocolAppRequirement => {
    const itemPath = `${path}.apps[${index}]`;
    if (!isRecord(item)) throw new Error(`${itemPath} must be an object`);
    rejectUnknownKeys(
      item,
      ["id", "platform", "packageId", "version", "requiresLogin"],
      itemPath,
    );
    return {
      id: requireString(item.id, `${itemPath}.id`),
      platform: enumField(
        item.platform,
        ["android", "harmonyos"] as const,
        `${itemPath}.platform`,
      ),
      ...(typeof item.packageId === "string" ? { packageId: item.packageId } : {}),
      ...(typeof item.version === "string" ? { version: item.version } : {}),
      requiresLogin: booleanField(item.requiresLogin, `${itemPath}.requiresLogin`),
    };
  });
  return {
    schemaVersion: "1.0",
    seed: requireNumber(value.seed, `${path}.seed`),
    repeats: requireNumber(value.repeats, `${path}.repeats`),
    taskOrder: {
      strategy: enumField(
        value.taskOrder.strategy,
        ["fixed", "seeded"] as const,
        `${path}.taskOrder.strategy`,
      ),
    },
    taskMaterialization: {
      reuseAcrossAgents: booleanField(
        value.taskMaterialization.reuseAcrossAgents,
        `${path}.taskMaterialization.reuseAcrossAgents`,
      ),
      strictFairness: booleanField(
        value.taskMaterialization.strictFairness,
        `${path}.taskMaterialization.strictFairness`,
      ),
    },
    device: {
      platform: enumField(
        value.device.platform,
        ["android", "harmonyos"] as const,
        `${path}.device.platform`,
      ),
      locale: requireString(value.device.locale, `${path}.device.locale`),
      orientation: enumField(
        value.device.orientation,
        ["portrait", "landscape", "any"] as const,
        `${path}.device.orientation`,
      ),
      versionPolicy: enumField(
        value.device.versionPolicy,
        ["exact", "compatible", "any"] as const,
        `${path}.device.versionPolicy`,
      ),
      ...(typeof value.device.osVersion === "string"
        ? { osVersion: value.device.osVersion }
        : {}),
    },
    apps,
    budget: {
      maxInteractions: requireNumber(
        value.budget.maxInteractions,
        `${path}.budget.maxInteractions`,
      ),
      maxActivations: requireNumber(
        value.budget.maxActivations,
        `${path}.budget.maxActivations`,
      ),
      timeoutSeconds: requireNumber(
        value.budget.timeoutSeconds,
        `${path}.budget.timeoutSeconds`,
      ),
      ...(typeof value.budget.tokenLimit === "number"
        ? {
            tokenLimit: requireNumber(
              value.budget.tokenLimit,
              `${path}.budget.tokenLimit`,
            ),
          }
        : {}),
      requireObservableTokens: booleanField(
        value.budget.requireObservableTokens,
        `${path}.budget.requireObservableTokens`,
      ),
    },
    isolation: {
      reset: enumField(
        value.isolation.reset,
        ["before_each_agent", "before_each_task", "once"] as const,
        `${path}.isolation.reset`,
      ),
      cleanup: enumField(
        value.isolation.cleanup,
        ["after_each_run", "after_each_task", "once"] as const,
        `${path}.isolation.cleanup`,
      ),
      requireVerifiedReset: booleanField(
        value.isolation.requireVerifiedReset,
        `${path}.isolation.requireVerifiedReset`,
      ),
    },
    failure: {
      initializer: parseFailureRule(
        value.failure.initializer,
        `${path}.failure.initializer`,
      ),
      agent: parseFailureRule(value.failure.agent, `${path}.failure.agent`),
      evaluator: parseFailureRule(
        value.failure.evaluator,
        `${path}.failure.evaluator`,
      ),
      cleanup: parseFailureRule(value.failure.cleanup, `${path}.failure.cleanup`),
    },
  };
}

/** Parse a deterministic preview response and reject silent contract drift. */
export function parseExperimentPreview(value: unknown): ExperimentPreview {
  if (!isRecord(value) || value.schemaVersion !== 1 || value.previewOnly !== true) {
    throw new Error("preview must be a schemaVersion 1 preview-only response");
  }
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "previewOnly",
      "previewFingerprint",
      "identities",
      "agentRevisions",
      "normalizedProtocol",
      "deviceProfileId",
      "executionLimits",
      "schedule",
      "diagnostics",
    ],
    "preview",
  );
  if (
    !isRecord(value.identities)
    || !Array.isArray(value.agentRevisions)
    || !isRecord(value.executionLimits)
    || !Array.isArray(value.schedule)
    || !Array.isArray(value.diagnostics)
  ) {
    throw new Error("preview collections and identities are invalid");
  }
  rejectUnknownKeys(
    value.identities,
    ["package", "packageContent", "benchmarkPlan", "experimentProtocol"],
    "preview.identities",
  );
  rejectUnknownKeys(
    value.executionLimits,
    ["maxAgents", "maxSelectedTasks", "maxRepeats", "multiAgentComparison"],
    "preview.executionLimits",
  );
  if (
    value.executionLimits.maxAgents !== 1
    || value.executionLimits.maxSelectedTasks !== 1
    || value.executionLimits.maxRepeats !== 1
    || value.executionLimits.multiAgentComparison !== false
  ) {
    throw new Error("preview execution limits are unsupported");
  }
  return {
    schemaVersion: 1,
    previewOnly: true,
    previewFingerprint: requireString(
      value.previewFingerprint,
      "preview.previewFingerprint",
    ),
    identities: {
      package: requireString(value.identities.package, "preview.identities.package"),
      packageContent: requireString(
        value.identities.packageContent,
        "preview.identities.packageContent",
      ),
      benchmarkPlan: requireString(
        value.identities.benchmarkPlan,
        "preview.identities.benchmarkPlan",
      ),
      experimentProtocol: requireString(
        value.identities.experimentProtocol,
        "preview.identities.experimentProtocol",
      ),
    },
    agentRevisions: value.agentRevisions.map((item, index) => {
      const path = `preview.agentRevisions[${index}]`;
      if (!isRecord(item)) throw new Error(`${path} must be an object`);
      rejectUnknownKeys(item, ["agentId", "revisionId", "agentGraph"], path);
      return {
        agentId: requireString(item.agentId, `${path}.agentId`),
        revisionId: requireString(item.revisionId, `${path}.revisionId`),
        agentGraph: requireString(item.agentGraph, `${path}.agentGraph`),
      };
    }),
    normalizedProtocol: parseExperimentProtocol(
      value.normalizedProtocol,
      "preview.normalizedProtocol",
    ),
    deviceProfileId: requireString(
      value.deviceProfileId,
      "preview.deviceProfileId",
    ),
    executionLimits: {
      maxAgents: 1,
      maxSelectedTasks: 1,
      maxRepeats: 1,
      multiAgentComparison: false,
    },
    schedule: value.schedule.map((item, index) => {
      const path = `preview.schedule[${index}]`;
      if (!isRecord(item) || !isRecord(item.taskInstance)) {
        throw new Error(`${path} must contain taskInstance`);
      }
      rejectUnknownKeys(
        item,
        [
          "plannedEntryId",
          "agentId",
          "revisionId",
          "taskId",
          "repeat",
          "order",
          "derivedSeed",
          "taskInstance",
        ],
        path,
      );
      rejectUnknownKeys(
        item.taskInstance,
        ["availability", "identity", "parameters"],
        `${path}.taskInstance`,
      );
      const availability = enumField(
        item.taskInstance.availability,
        ["pending_materialization", "template_only"] as const,
        `${path}.taskInstance.availability`,
      );
      if (
        (item.taskInstance.identity !== null
          && item.taskInstance.identity !== undefined)
        || (item.taskInstance.parameters !== null
          && item.taskInstance.parameters !== undefined)
      ) {
        throw new Error(`${path}.taskInstance must remain unmaterialized`);
      }
      return {
        plannedEntryId: requireString(
          item.plannedEntryId,
          `${path}.plannedEntryId`,
        ),
        agentId: requireString(item.agentId, `${path}.agentId`),
        revisionId: requireString(item.revisionId, `${path}.revisionId`),
        taskId: requireString(item.taskId, `${path}.taskId`),
        repeat: requireNumber(item.repeat, `${path}.repeat`),
        order: requireNumber(item.order, `${path}.order`),
        derivedSeed: requireNumber(item.derivedSeed, `${path}.derivedSeed`),
        taskInstance: {
          availability,
          identity: null,
          parameters: null,
        },
      };
    }),
    diagnostics: value.diagnostics.map((item, index) =>
      parseBenchmarkDiagnostic(item, `preview.diagnostics[${index}]`),
    ),
  };
}
