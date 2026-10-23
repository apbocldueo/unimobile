import { describe, expect, it } from "vitest";
import {
  parseExactRevisionReadiness,
  parseRuntimeEnvironmentReadiness,
} from "./runtimeReadiness.schema";

const hash = `sha256:${"a".repeat(64)}`;

describe("runtime readiness parsers", () => {
  it("accepts safe presence-only process and exact projections", () => {
    const process = parseRuntimeEnvironmentReadiness({
      schemaVersion: 1,
      ready: false,
      providers: [{
        identifier: "llm:openai_llm@1.0.0",
        category: "runtime_service",
        available: true,
        errorType: "",
      }],
      secrets: [{ secretRef: "openai_api_key", configured: false }],
      deviceProfiles: [{
        deviceProfileId: "research-android",
        label: "Research Android",
        platform: "android",
        availability: "configured",
      }],
      diagnostics: [{
        code: "studio.readiness.secret_missing",
        category: "secret",
        message: "A known SecretRef is not configured",
        subjectIdentity: "openai_api_key",
        remediationKey: "configure-studio-secrets",
      }],
    });
    const exact = parseExactRevisionReadiness({
      schemaVersion: 1,
      agentId: "agent-1",
      revisionId: "revision-1",
      canonicalHash: hash,
      deviceProfileId: "research-android",
      ready: false,
      diagnostics: [{
        code: "studio.readiness.topology_feedback_missing",
        category: "topology",
        message: "Nonterminal execution must return to DeviceObserve",
        subjectIdentity: null,
        nodeId: "action_executor",
        remediationKey: "repair-studio-android-topology",
      }],
    });
    expect(process.secrets).toEqual([{ secretRef: "openai_api_key", configured: false }]);
    expect(exact.canonicalHash).toBe(hash);
    expect(exact.diagnostics[0]).toMatchObject({
      category: "topology",
      nodeId: "action_executor",
    });
    expect(JSON.stringify({ process, exact })).not.toContain("api-key-value");
  });

  it("fails closed on malformed or expanded payloads", () => {
    expect(() => parseRuntimeEnvironmentReadiness({
      schemaVersion: 1,
      ready: true,
      providers: [],
      secrets: [],
      deviceProfiles: [],
      diagnostics: [],
      rawSerial: "emulator-5554",
    })).toThrow(/rawSerial/);
    expect(() => parseExactRevisionReadiness({
      schemaVersion: 1,
      agentId: "agent-1",
      revisionId: "revision-1",
      canonicalHash: "not-a-hash",
      deviceProfileId: "research-android",
      ready: true,
      diagnostics: [],
    })).toThrow(/canonicalHash/);
  });
});
