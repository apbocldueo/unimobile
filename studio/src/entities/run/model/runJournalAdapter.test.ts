import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { AgentRevision } from "@/entities/agent-revision";
import {
  createEmptyStudioDocument,
  STUDIO_CAPABILITY_AUTHORING_POLICY,
  STUDIO_CAPABILITY_LOWERING_PROFILE,
} from "@/entities/agent-graph";
import type { ReplayEnvelope } from "@/entities/replay";
import {
  adaptRevisionToRunSnapshot,
  adaptRunJournal,
  createReplayProjection,
  finalizeRunEvidenceProjection,
  parseStudioRunEvent,
  parseStudioRunEventPage,
  projectReplay,
  reduceReplayMoment,
  type StudioRunResource,
} from "@/entities/run";
import { parseReplayEnvelope } from "@/entities/replay";

const runId = `run-${"a".repeat(32)}`;
const hash = `sha256:${"b".repeat(64)}`;
const artifactId = `artifact-${"c".repeat(32)}`;

/**
 * Build one strict journal event through the public parser.
 *
 * @param sequence Durable event sequence.
 * @param kind Formal event kind.
 * @param payload Safe persisted payload.
 * @param activationId Optional activation identity.
 * @param interactionStep Explicit causal interaction position.
 */
function event(
  sequence: number,
  kind: string,
  payload: Record<string, unknown>,
  activationId = "",
  interactionStep = 0,
) {
  return parseStudioRunEvent({
    schemaVersion: 1,
    eventId: `event-${sequence}`,
    timestamp: sequence,
    source: kind === "run.terminal" ? "result" : "runtime",
    kind,
    payload,
    runtimeSequence: sequence,
    nodePath: activationId ? "reasoning" : "",
    activationId,
    interactionStep,
    runId,
    sequence,
    fingerprint: hash,
  });
}

/** Build the shared snapshot fixture used by live and Replay projections. */
function snapshot() {
  return {
    agentId: "agent-1",
    revisionId: "revision-1",
    contractVersion: "1.1",
    canonicalHash: hash,
    graphStatus: "available" as const,
    agentGraph: { nodes: [], edges: [] },
    graphNodes: [
      {
        id: "reasoning",
        kind: "component",
        role: "zhixing.role.reasoning",
        lifecycle: "per_step",
        primary: false,
      },
      {
        id: "never-ran",
        kind: "component",
        role: "zhixing.role.verifier",
        lifecycle: "post_action",
        primary: false,
      },
    ],
    graphEdges: [],
    presentation: null,
    sourceMap: [],
    providerIdentities: [],
  };
}

describe("Run journal adapter", () => {
  it("matches the backend-validated same-source native Replay fixture", () => {
    const raw = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          "src/entities/run/model/fixtures/live-replay-same-source.json",
        ),
        "utf-8",
      ),
    ) as { journalPage: unknown; replay: unknown };
    const page = parseStudioRunEventPage(raw.journalPage);
    const replay = parseReplayEnvelope(raw.replay);
    const evidence = adaptRunJournal(page.items);
    expect(evidence.moments).toEqual(replay.moments);
    expect(evidence.observations).toEqual(replay.observations);
    expect(evidence.actions).toEqual(replay.actions);
  });

  it("correlates observation, action, and typed Debug evidence by formal facts", () => {
    const evidence = adaptRunJournal([
      event(1, "complete", {
        role: "zhixing.service.device_observe",
        outputs: {
          screenshot_artifact: artifactId,
          width: 1080,
          height: 1920,
          platform: "android",
          device_id: "device-sha256:fixture",
        },
      }),
      event(2, "complete", {
        role: "zhixing.service.action_executor",
        outputs: {
          status: "success",
          action_type: "tap",
          effect_performed: true,
        },
        artifactIds: [artifactId],
      }),
      event(
        3,
        "component.debug.complete",
        {
          schemaVersion: 1,
          debugId: "debug-1",
          runId,
          nodePath: "reasoning",
          activationId: "activation-1",
          componentIdentity: "fixture:reasoner@1.0.0",
          role: "zhixing.role.reasoning",
          stage: "complete",
          task: "Open Settings",
          inputSummary: {},
          outputSummary: {},
          durationMs: 5,
          error: "",
          usage: {},
          artifactIds: [artifactId],
          evidenceRefs: {
            modelResponse: {
              schemaVersion: 1,
              kind: "model_response",
              artifactId,
              availability: "available",
              contentType: "text/plain",
              size: 4,
              originalSize: null,
              sha256: hash,
              provenance: "component_invocation",
              causalIdentity: "debug-1",
              hidden: false,
            },
          },
          availability: { modelResponse: "available" },
          diagnostics: [],
        },
        "activation-1",
      ),
    ]);
    expect(evidence.observations[0]).toMatchObject({
      observationId: "observation-00000001",
      screenshotArtifactId: artifactId,
    });
    expect(evidence.actions[0]).toMatchObject({
      actionId: "action-00000002",
      actionType: "tap",
      artifactId,
    });
    expect(evidence.moments[2]?.debugPayload?.activationId).toBe("activation-1");
  });

  it("orders repeated formal activations and ignores screenshot-like display names", () => {
    const evidence = adaptRunJournal([
      event(1, "complete", {
        role: "zhixing.service.device_observe",
        node_id: "observe",
        outputs: {
          sequence: 0,
          screenshot_artifact: `artifact-${"1".repeat(32)}`,
          width: 100,
          height: 200,
        },
      }, "observe-1", 0),
      event(2, "complete", {
        role: "zhixing.service.action_executor",
        node_id: "action_executor",
        outputs: {
          status: "success",
          action_type: "tap",
          effect_performed: true,
          terminal_status: null,
        },
      }, "action-1", 0),
      event(3, "feedback_iteration", {
        role: "zhixing.service.action_executor",
        node_id: "action_executor",
        loop_path: "action_executor->memory",
        loop_iteration: 1,
      }, "action-1", 0),
      event(4, "complete", {
        role: "zhixing.service.device_observe",
        node_id: "observe",
        outputs: {
          sequence: 1,
          screenshot_artifact: `artifact-${"2".repeat(32)}`,
          width: 100,
          height: 200,
        },
      }, "observe-2", 1),
      event(5, "complete", {
        role: "fixture.screenshot_card",
        component: "Friendly DeviceObserve Display Name",
        outputs: {
          screenshot_artifact: `artifact-${"3".repeat(32)}`,
        },
      }, "not-observe", 1),
      event(6, "complete", {
        role: "zhixing.service.action_executor",
        node_id: "action_executor",
        outputs: {
          status: "terminal",
          action_type: "done",
          effect_performed: false,
          terminal_status: "success",
        },
      }, "action-2", 1),
    ]);

    expect(evidence.observations.map((item) => [item.sequence, item.interactionStep])).toEqual([
      [0, 0],
      [1, 1],
    ]);
    expect(evidence.actions.map((item) => [item.actionType, item.terminalStatus])).toEqual([
      ["tap", null],
      ["done", "success"],
    ]);
    expect(evidence.moments[2]).toMatchObject({
      sourceKind: "action",
      loopIteration: 1,
    });
    expect(evidence.moments[4]?.sourceKind).toBe("agent_graph");
  });

  it.each([
    ["complete", "success"],
    ["fail", "failure"],
    ["cancellation_requested", "cancelled"],
    ["loop_exhausted", "step_limit"],
    ["service_restarted", "failure"],
  ])(
    "keeps terminal live and Replay projections deeply equivalent for %s",
    (terminalKind, status) => {
      const events = [
        event(
          1,
          "start",
          {
            role: "zhixing.role.reasoning",
            component: "fixture:reasoner@1.0.0",
            node_id: "reasoning",
          },
          "activation-1",
        ),
        event(
          2,
          terminalKind,
          {
            role: "zhixing.role.reasoning",
            component: "fixture:reasoner@1.0.0",
            node_id: "reasoning",
            loop_path: terminalKind === "loop_exhausted" ? "loop" : "",
          },
          "activation-1",
        ),
      ];
      const evidence = adaptRunJournal(events);
      const result = {
        status,
        kernelStatus: status,
        error: status === "success" ? "" : status,
        stepCount: 1,
        activationCount: 1,
        interactionCount: 0,
        usage: {},
      };
      const replay: ReplayEnvelope = {
        schemaVersion: 1,
        runId,
        importedAt: 3,
        provenance: "native_replay_package",
        evidenceOrigin: {
          schemaVersion: 1,
          acquisition: "replay_projection",
          environment: "unverified",
          deviceProfileId: null,
          deviceChecks: [],
          realDeviceEvidence: false,
        },
        integrityState: "complete",
        snapshot: snapshot(),
        result,
        moments: evidence.moments,
        observations: evidence.observations,
        actions: evidence.actions,
        benchmark: null,
        artifacts: [],
        availability: {},
        integrity: [],
      };
      const replayProjection = projectReplay(replay);
      let liveProjection = createReplayProjection(
        replay.snapshot,
        replay.result,
        null,
        replay.observations,
        replay.actions,
        replay.availability,
        replay.integrityState,
      );
      evidence.moments.forEach((moment) => {
        liveProjection = reduceReplayMoment(liveProjection, moment);
      });
      liveProjection = finalizeRunEvidenceProjection(
        liveProjection,
        result,
        null,
      );
      expect(liveProjection).toEqual(replayProjection);
      expect(liveProjection.nodesById["never-ran"]?.status).toBe("not_observed");
    },
  );
});

describe("exact revision snapshot adapter", () => {
  it("requires agent, revision, valid compile, and canonical hash parity", () => {
    const baseDocument = createEmptyStudioDocument("agent-1", "Agent", "document-1");
    const revision = {
      revisionId: "revision-1",
      agentId: "agent-1",
      compileSnapshot: {
        status: "valid",
        diagnostics: [],
        sourceMap: [],
        authoringPolicy: STUDIO_CAPABILITY_AUTHORING_POLICY,
        loweringProfile: STUDIO_CAPABILITY_LOWERING_PROFILE,
        capabilityHash: `sha256:${"c".repeat(64)}`,
        projectionMap: [{
          graphKind: "node",
          graphId: "reasoning",
          owner: { kind: "capability", ownerId: "reasoning" },
          propertyPath: [],
        }],
        canonicalHash: hash,
        agentGraph: {
          nodes: [
            {
              id: "reasoning",
              kind: "component",
              role: "zhixing.role.reasoning",
              lifecycle: "per_step",
              primary: false,
            },
          ],
          edges: [],
        },
      },
      document: {
        ...baseDocument,
        capabilities: [{
          canvasId: "canvas-reasoning",
          logicalId: "reasoning",
          family: "reasoning",
          lifecycle: "per_step",
          implementation: {
            policy: "single",
            candidates: [{
              namespace: "agent.reasoning",
              name: "universal_reasoning",
              version: "1",
              params: {},
              dependencies: {},
            }],
          },
        }],
        presentation: {
          nodes: {},
          viewport: { x: 0, y: 0, zoom: 1 },
        },
      },
    } as unknown as AgentRevision;
    const run = {
      agentId: "agent-1",
      revisionId: "revision-1",
      canonicalHash: hash,
    } as StudioRunResource;
    expect(adaptRevisionToRunSnapshot(revision, run).graphNodes[0]?.id).toBe(
      "reasoning",
    );
    expect(() =>
      adaptRevisionToRunSnapshot(
        revision,
        { ...run, canonicalHash: `sha256:${"d".repeat(64)}` },
      ),
    ).toThrow(/canonical hash/);
    expect(() =>
      adaptRevisionToRunSnapshot(
        { ...revision, agentId: "agent-other" },
        run,
      ),
    ).toThrow(/Agent identity/);
  });
});
