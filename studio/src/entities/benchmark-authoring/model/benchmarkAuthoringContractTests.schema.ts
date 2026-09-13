import {
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
} from "@/shared/lib";
import {
  parseBenchmarkAnalysisDiagnostic,
  parseBenchmarkAnalysisIdentities,
  type BenchmarkAnalysisDiagnostic,
  type BenchmarkAnalysisIdentities,
} from "./benchmarkAuthoringAnalysis.schema";

export const BENCHMARK_CONTRACT_MAX_CASES = 1_000;
export const BENCHMARK_CONTRACT_MAX_DIAGNOSTICS = 100;
export const BENCHMARK_CONTRACT_MAX_PROFILES = 32;

const DRAFT_ID = /^benchmark-draft-[a-f0-9]{32}$/;
const REVISION_ID = /^benchmark-authoring-revision-[a-f0-9]{32}$/;
const STABLE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const PACKAGE_PATH = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))(?!.*\\)(?!.*\/\/)[^\0]+$/;

export type BenchmarkContractKind = "initializer" | "environment" | "evaluator";
export type BenchmarkContractStatus = "passed" | "failed" | "skipped";

export type BenchmarkContractTestProfile = {
  profileId: string;
  version: string;
  title: string;
  description: string;
  evidenceLevel: string;
  supportedKinds: BenchmarkContractKind[];
  capabilities: string[];
};

export type BenchmarkContractTestProfilePage = {
  schemaVersion: 1;
  profiles: BenchmarkContractTestProfile[];
};

export type BenchmarkContractTestRequest = {
  schemaVersion: 1;
  revisionId: string;
  split: string;
  seed: number;
  fixtureProfileId: string;
};

export type BenchmarkContractTestDiagnostic = {
  code: string;
  message: string;
  memberKind: "manifest" | "task" | "protocol";
  memberPath: string | null;
  fieldPath: Array<string | number>;
  taskId: string | null;
};

export type BenchmarkContractTestCase = {
  caseId: string;
  taskId: string;
  kind: BenchmarkContractKind;
  logicalName: string;
  memberPath: string | null;
  fieldPath: Array<string | number>;
  phase: "reset" | "setup" | "cleanup" | "evaluation" | null;
  seed: number;
  status: BenchmarkContractStatus;
  fixtureId: string | null;
  fixtureVersion: string | null;
  checks: string[];
  skipped: string[];
  diagnostics: BenchmarkContractTestDiagnostic[];
};

export type BenchmarkContractTestCoverage = {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  complete: boolean;
  executedChecksPassed: boolean;
};

export type BenchmarkContractTestSafety = {
  fixtureExecution: true;
  packageCodeExecuted: false;
  realDeviceEvidence: false;
  processSandbox: false;
  deviceCapability: false;
  modelCapability: false;
  networkCapability: false;
  secretCapability: false;
  runtimeCapability: false;
  experimentCapability: false;
  outputPathCapability: false;
  benchmarkExecution: false;
  agentExecution: false;
  publicationEligibility: false;
  resultPersisted: false;
};

export type BenchmarkContractTestResult = {
  schemaVersion: 1;
  mode: "fake-fixture";
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  requestFingerprint: string;
  split: string;
  seed: number;
  profile: BenchmarkContractTestProfile;
  identities: BenchmarkAnalysisIdentities;
  validDefinition: boolean;
  coverage: BenchmarkContractTestCoverage;
  cases: BenchmarkContractTestCase[];
  preconditionDiagnostics: BenchmarkAnalysisDiagnostic[];
  diagnosticsTruncated: boolean;
  safety: BenchmarkContractTestSafety;
};

/** Require one safe bounded string. */
function boundedString(value: unknown, path: string, maximum: number): string {
  const text = requireString(value, path);
  if (text.length === 0 || text.length > maximum || /[\r\n\0]/.test(text)) {
    throw new Error(`${path} is not bounded safe text`);
  }
  return text;
}

/** Require one safe matching string. */
function matchingString(value: unknown, pattern: RegExp, path: string): string {
  const text = requireString(value, path);
  if (!pattern.test(text)) throw new Error(`${path} is malformed`);
  return text;
}

/** Require one inclusive bounded safe integer. */
function boundedInteger(
  value: unknown,
  minimum: number,
  maximum: number,
  path: string,
): number {
  const parsed = requireNumber(value, path);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${path} is outside its integer bound`);
  }
  return parsed;
}

/** Parse one bounded unique string array. */
function stringArray(
  value: unknown,
  path: string,
  maximum: number,
): string[] {
  if (!Array.isArray(value) || value.length > maximum) {
    throw new Error(`${path} exceeds its collection bound`);
  }
  const result = value.map((item, index) =>
    boundedString(item, `${path}[${index}]`, 160));
  if (new Set(result).size !== result.length) {
    throw new Error(`${path} contains duplicates`);
  }
  return result;
}

/** Parse one safe member-local field breadcrumb. */
function fieldPath(value: unknown, path: string): Array<string | number> {
  if (!Array.isArray(value) || value.length > 16) {
    throw new Error(`${path} exceeds its path bound`);
  }
  return value.map((item, index) => {
    if (typeof item === "string") return boundedString(item, `${path}[${index}]`, 160);
    if (typeof item !== "number" || !Number.isSafeInteger(item) || item < 0) {
      throw new Error(`${path}[${index}] is not a safe segment`);
    }
    return item;
  });
}

/** Parse one metadata-only trusted fixture profile. */
export function parseBenchmarkContractTestProfile(
  value: unknown,
  path = "contractTestProfile",
): BenchmarkContractTestProfile {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, [
    "profileId", "version", "title", "description", "evidenceLevel",
    "supportedKinds", "capabilities",
  ], path);
  if (!Array.isArray(value.supportedKinds) || value.supportedKinds.length === 0 || value.supportedKinds.length > 3) {
    throw new Error(`${path}.supportedKinds is invalid`);
  }
  const supportedKinds = value.supportedKinds.map((item, index) => {
    if (item !== "initializer" && item !== "environment" && item !== "evaluator") {
      throw new Error(`${path}.supportedKinds[${index}] is unsupported`);
    }
    return item;
  });
  if (new Set(supportedKinds).size !== supportedKinds.length
    || supportedKinds.join("\0") !== [...supportedKinds].sort().join("\0")) {
    throw new Error(`${path}.supportedKinds must be unique and sorted`);
  }
  const capabilities = stringArray(value.capabilities, `${path}.capabilities`, 16);
  if (capabilities.join("\0") !== [...capabilities].sort().join("\0")) {
    throw new Error(`${path}.capabilities must be sorted`);
  }
  const description = requireString(value.description, `${path}.description`);
  if (description.length > 500 || /[\r\n\0]/.test(description)) {
    throw new Error(`${path}.description is not bounded safe text`);
  }
  return {
    profileId: matchingString(value.profileId, STABLE_ID, `${path}.profileId`),
    version: matchingString(value.version, SEMVER, `${path}.version`),
    title: boundedString(value.title, `${path}.title`, 120),
    description,
    evidenceLevel: matchingString(value.evidenceLevel, STABLE_ID, `${path}.evidenceLevel`),
    supportedKinds,
    capabilities,
  };
}

/** Parse the bounded profile metadata resource. */
export function parseBenchmarkContractTestProfilePage(
  value: unknown,
): BenchmarkContractTestProfilePage {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error("contractTestProfilePage must be schemaVersion 1");
  }
  rejectUnknownKeys(value, ["schemaVersion", "profiles"], "contractTestProfilePage");
  if (!Array.isArray(value.profiles) || value.profiles.length > BENCHMARK_CONTRACT_MAX_PROFILES) {
    throw new Error("contractTestProfilePage.profiles exceeds its bound");
  }
  const profiles = value.profiles.map((item, index) =>
    parseBenchmarkContractTestProfile(item, `contractTestProfilePage.profiles[${index}]`));
  const keys = profiles.map((item) => `${item.profileId}\0${item.version}`);
  if (new Set(keys).size !== keys.length || keys.join("\0") !== [...keys].sort().join("\0")) {
    throw new Error("contractTestProfilePage.profiles must be unique and sorted");
  }
  return { schemaVersion: 1, profiles };
}

/** Parse one case-local safe diagnostic. */
function parseCaseDiagnostic(
  value: unknown,
  path: string,
): BenchmarkContractTestDiagnostic {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, [
    "code", "message", "memberKind", "memberPath", "fieldPath", "taskId",
  ], path);
  if (value.memberKind !== "manifest" && value.memberKind !== "task" && value.memberKind !== "protocol") {
    throw new Error(`${path}.memberKind is unsupported`);
  }
  return {
    code: boundedString(value.code, `${path}.code`, 160),
    message: boundedString(value.message, `${path}.message`, 500),
    memberKind: value.memberKind,
    memberPath: value.memberPath === undefined || value.memberPath === null
      ? null
      : matchingString(value.memberPath, PACKAGE_PATH, `${path}.memberPath`),
    fieldPath: fieldPath(value.fieldPath ?? [], `${path}.fieldPath`),
    taskId: value.taskId === undefined || value.taskId === null
      ? null
      : boundedString(value.taskId, `${path}.taskId`, 256),
  };
}

/** Parse one bounded stable Contract Test occurrence. */
function parseCase(value: unknown, path: string): BenchmarkContractTestCase {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, [
    "caseId", "taskId", "kind", "logicalName", "memberPath", "fieldPath",
    "phase", "seed", "status", "fixtureId", "fixtureVersion", "checks",
    "skipped", "diagnostics",
  ], path);
  if (value.kind !== "initializer" && value.kind !== "environment" && value.kind !== "evaluator") {
    throw new Error(`${path}.kind is unsupported`);
  }
  if (value.status !== "passed" && value.status !== "failed" && value.status !== "skipped") {
    throw new Error(`${path}.status is unsupported`);
  }
  const phase = value.phase === undefined || value.phase === null ? null : value.phase;
  if (phase !== null && phase !== "reset" && phase !== "setup" && phase !== "cleanup" && phase !== "evaluation") {
    throw new Error(`${path}.phase is unsupported`);
  }
  const fixtureId = value.fixtureId === undefined || value.fixtureId === null
    ? null : matchingString(value.fixtureId, STABLE_ID, `${path}.fixtureId`);
  const fixtureVersion = value.fixtureVersion === undefined || value.fixtureVersion === null
    ? null : matchingString(value.fixtureVersion, SEMVER, `${path}.fixtureVersion`);
  const checks = stringArray(value.checks ?? [], `${path}.checks`, 32);
  const skipped = stringArray(value.skipped ?? [], `${path}.skipped`, 32);
  if (!Array.isArray(value.diagnostics) || value.diagnostics.length > BENCHMARK_CONTRACT_MAX_DIAGNOSTICS) {
    throw new Error(`${path}.diagnostics exceeds its bound`);
  }
  const diagnostics = value.diagnostics.map((item, index) =>
    parseCaseDiagnostic(item, `${path}.diagnostics[${index}]`));
  if ((fixtureId === null) !== (fixtureVersion === null)) {
    throw new Error(`${path} fixture provenance is partial`);
  }
  if (value.status === "passed" && (fixtureId === null || diagnostics.length > 0 || skipped.length > 0)) {
    throw new Error(`${path} passed evidence contradicts status`);
  }
  if (value.status === "failed" && (fixtureId === null || diagnostics.length === 0 || skipped.length > 0)) {
    throw new Error(`${path} failed evidence contradicts status`);
  }
  if (value.status === "skipped" && (fixtureId !== null || skipped.length === 0)) {
    throw new Error(`${path} skipped evidence contradicts status`);
  }
  return {
    caseId: matchingString(value.caseId, DIGEST, `${path}.caseId`),
    taskId: boundedString(value.taskId, `${path}.taskId`, 256),
    kind: value.kind,
    logicalName: boundedString(value.logicalName, `${path}.logicalName`, 160),
    memberPath: value.memberPath === undefined || value.memberPath === null
      ? null : matchingString(value.memberPath, PACKAGE_PATH, `${path}.memberPath`),
    fieldPath: fieldPath(value.fieldPath ?? [], `${path}.fieldPath`),
    phase,
    seed: boundedInteger(value.seed, 0, Number.MAX_SAFE_INTEGER, `${path}.seed`),
    status: value.status,
    fixtureId,
    fixtureVersion,
    checks,
    skipped,
    diagnostics,
  };
}

/** Parse internally consistent aggregate coverage. */
function parseCoverage(value: unknown): BenchmarkContractTestCoverage {
  const path = "contractTestResult.coverage";
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, [
    "total", "passed", "failed", "skipped", "complete", "executedChecksPassed",
  ], path);
  const result = {
    total: boundedInteger(value.total, 0, BENCHMARK_CONTRACT_MAX_CASES, `${path}.total`),
    passed: boundedInteger(value.passed, 0, BENCHMARK_CONTRACT_MAX_CASES, `${path}.passed`),
    failed: boundedInteger(value.failed, 0, BENCHMARK_CONTRACT_MAX_CASES, `${path}.failed`),
    skipped: boundedInteger(value.skipped, 0, BENCHMARK_CONTRACT_MAX_CASES, `${path}.skipped`),
    complete: value.complete,
    executedChecksPassed: value.executedChecksPassed,
  };
  if (typeof result.complete !== "boolean" || typeof result.executedChecksPassed !== "boolean") {
    throw new Error(`${path} booleans are invalid`);
  }
  if (result.total !== result.passed + result.failed + result.skipped
    || result.complete !== (result.skipped === 0)
    || result.executedChecksPassed !== (result.failed === 0)) {
    throw new Error(`${path} contains contradictory facts`);
  }
  return result as BenchmarkContractTestCoverage;
}

/** Parse fixed non-runtime safety facts and reject stronger claims. */
function parseSafety(value: unknown): BenchmarkContractTestSafety {
  const path = "contractTestResult.safety";
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  const expected = {
    fixtureExecution: true,
    packageCodeExecuted: false,
    realDeviceEvidence: false,
    processSandbox: false,
    deviceCapability: false,
    modelCapability: false,
    networkCapability: false,
    secretCapability: false,
    runtimeCapability: false,
    experimentCapability: false,
    outputPathCapability: false,
    benchmarkExecution: false,
    agentExecution: false,
    publicationEligibility: false,
    resultPersisted: false,
  } as const;
  rejectUnknownKeys(value, Object.keys(expected), path);
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (value[key] !== expectedValue) throw new Error(`${path}.${key} is misleading`);
  }
  return expected;
}

/** Parse one strict closed Contract Test result. */
export function parseBenchmarkContractTestResult(
  value: unknown,
): BenchmarkContractTestResult {
  const path = "contractTestResult";
  if (!isRecord(value) || value.schemaVersion !== 1 || value.mode !== "fake-fixture") {
    throw new Error(`${path} must be a schemaVersion 1 fake-fixture result`);
  }
  rejectUnknownKeys(value, [
    "schemaVersion", "mode", "draftId", "revisionId", "documentFingerprint",
    "requestFingerprint", "split", "seed", "profile", "identities",
    "validDefinition", "coverage", "cases", "preconditionDiagnostics",
    "diagnosticsTruncated", "safety",
  ], path);
  if (!Array.isArray(value.cases) || value.cases.length > BENCHMARK_CONTRACT_MAX_CASES) {
    throw new Error(`${path}.cases exceeds its bound`);
  }
  const cases = value.cases.map((item, index) => parseCase(item, `${path}.cases[${index}]`));
  if (!Array.isArray(value.preconditionDiagnostics)
    || value.preconditionDiagnostics.length > BENCHMARK_CONTRACT_MAX_DIAGNOSTICS) {
    throw new Error(`${path}.preconditionDiagnostics exceeds its bound`);
  }
  const preconditionDiagnostics = value.preconditionDiagnostics.map((item, index) =>
    parseBenchmarkAnalysisDiagnostic(item, `${path}.preconditionDiagnostics[${index}]`));
  const coverage = parseCoverage(value.coverage);
  const diagnosticCount = preconditionDiagnostics.length
    + cases.reduce((count, item) => count + item.diagnostics.length, 0);
  if (cases.length !== coverage.total || diagnosticCount > BENCHMARK_CONTRACT_MAX_DIAGNOSTICS) {
    throw new Error(`${path} violates collection ownership bounds`);
  }
  const counts = {
    passed: cases.filter((item) => item.status === "passed").length,
    failed: cases.filter((item) => item.status === "failed").length,
    skipped: cases.filter((item) => item.status === "skipped").length,
  };
  if (counts.passed !== coverage.passed || counts.failed !== coverage.failed || counts.skipped !== coverage.skipped) {
    throw new Error(`${path}.cases contradict aggregate coverage`);
  }
  if (typeof value.validDefinition !== "boolean" || typeof value.diagnosticsTruncated !== "boolean") {
    throw new Error(`${path} boolean facts are invalid`);
  }
  if (value.validDefinition === false && (cases.length > 0 || preconditionDiagnostics.length === 0)) {
    throw new Error(`${path} invalid definition contains partial fixture facts`);
  }
  if (value.validDefinition === true && preconditionDiagnostics.length > 0) {
    throw new Error(`${path} valid definition contains precondition errors`);
  }
  return {
    schemaVersion: 1,
    mode: "fake-fixture",
    draftId: matchingString(value.draftId, DRAFT_ID, `${path}.draftId`),
    revisionId: matchingString(value.revisionId, REVISION_ID, `${path}.revisionId`),
    documentFingerprint: matchingString(value.documentFingerprint, DIGEST, `${path}.documentFingerprint`),
    requestFingerprint: matchingString(value.requestFingerprint, DIGEST, `${path}.requestFingerprint`),
    split: boundedString(value.split, `${path}.split`, 128),
    seed: boundedInteger(value.seed, Number.MIN_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, `${path}.seed`),
    profile: parseBenchmarkContractTestProfile(value.profile, `${path}.profile`),
    identities: parseBenchmarkAnalysisIdentities(value.identities, `${path}.identities`),
    validDefinition: value.validDefinition,
    coverage,
    cases,
    preconditionDiagnostics,
    diagnosticsTruncated: value.diagnosticsTruncated,
    safety: parseSafety(value.safety),
  };
}
