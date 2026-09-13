import { describe, expect, it } from "vitest";
import type { StudioAgent } from "@/entities/agent";
import {
  benchmarkAgentFixtureId,
  benchmarkAgentRevisionFixtureId,
  benchmarkDigestFixture,
  benchmarkDraftFixtureId,
  benchmarkDryRunResultFixture,
  benchmarkRevisionFixtureId,
  benchmarkValidationResultFixture,
} from "@/entities/benchmark-authoring";
import {
  acceptBenchmarkDryRunResult,
  acceptBenchmarkValidationResult,
  addFrozenAgentRevision,
  benchmarkDryRunRequestOwner,
  benchmarkValidationRequestOwner,
  createBenchmarkAnalysisSession,
  reconcileBenchmarkAnalysisSession,
  removeFrozenAgentRevision,
  setBenchmarkAnalysisSplit,
  setBenchmarkAnalysisTasks,
} from "@/features/benchmark-validation-dry-run";

/** Build one mutable Agent metadata candidate for selection tests. */
function agent(
  agentId = benchmarkAgentFixtureId,
  revisionId: string | null = benchmarkAgentRevisionFixtureId,
): StudioAgent {
  return {
    agentId,
    name: `Agent ${agentId}`,
    currentRevisionId: revisionId,
    createdAt: 1,
    updatedAt: 1,
  };
}

/** Build the canonical current-revision analysis session. */
function session() {
  return createBenchmarkAnalysisSession({
    draftId: benchmarkDraftFixtureId,
    revisionId: benchmarkRevisionFixtureId,
    documentFingerprint: benchmarkDigestFixture,
    split: "test",
  });
}

describe("benchmark analysis session", () => {
  it("freezes Agent revisions and never advances them on metadata refresh", () => {
    const selected = addFrozenAgentRevision(session(), agent());
    const refreshed = addFrozenAgentRevision(
      selected,
      agent(benchmarkAgentFixtureId, "revision-new-current"),
    );
    expect(refreshed.agentRevisions).toEqual([
      expect.objectContaining({ revisionId: benchmarkAgentRevisionFixtureId }),
    ]);
    expect(removeFrozenAgentRevision(refreshed, benchmarkAgentFixtureId).agentRevisions)
      .toEqual([]);
  });

  it("blocks missing, duplicate, and seventeenth Agent dimensions", () => {
    expect(addFrozenAgentRevision(session(), agent("agent-empty", null)).agentRevisions)
      .toHaveLength(0);
    let selected = session();
    for (let index = 0; index < 17; index += 1) {
      selected = addFrozenAgentRevision(
        selected,
        agent(`agent-${index}`, `revision-${index}`),
      );
    }
    expect(selected.agentRevisions).toHaveLength(16);
  });

  it("keeps validation ownership stable across task and Agent input changes", () => {
    const initial = session();
    const validationOwner = benchmarkValidationRequestOwner(initial);
    const dryOwner = benchmarkDryRunRequestOwner(initial);
    const changed = addFrozenAgentRevision(
      setBenchmarkAnalysisTasks(initial, ["fixture-task"]),
      agent(),
    );
    expect(benchmarkValidationRequestOwner(changed).key).toBe(validationOwner.key);
    expect(benchmarkDryRunRequestOwner(changed).key).not.toBe(dryOwner.key);
  });

  it("discards late results after relevant input movement", () => {
    const initial = session();
    const validationOwner = benchmarkValidationRequestOwner(initial);
    const movedSplit = setBenchmarkAnalysisSplit(initial, "other");
    expect(
      acceptBenchmarkValidationResult(
        movedSplit,
        validationOwner,
        benchmarkValidationResultFixture(),
      ).validationResult,
    ).toBeNull();

    const selected = addFrozenAgentRevision(initial, agent());
    const dryOwner = benchmarkDryRunRequestOwner(selected);
    const movedTasks = setBenchmarkAnalysisTasks(selected, ["different-task"]);
    expect(
      acceptBenchmarkDryRunResult(
        movedTasks,
        dryOwner,
        benchmarkDryRunResultFixture(),
      ).dryRunResult,
    ).toBeNull();
  });

  it("accepts matching facts and clears all state for another revision owner", () => {
    const validationOwner = benchmarkValidationRequestOwner(session());
    const validated = acceptBenchmarkValidationResult(
      session(),
      validationOwner,
      benchmarkValidationResultFixture(),
    );
    expect(validated.validationResult?.valid).toBe(false);

    const selected = addFrozenAgentRevision(validated, agent());
    const planned = acceptBenchmarkDryRunResult(
      selected,
      benchmarkDryRunRequestOwner(selected),
      benchmarkDryRunResultFixture(),
    );
    expect(planned.dryRunResult?.schedule).toHaveLength(1);

    const reconciled = reconcileBenchmarkAnalysisSession(planned, {
      draftId: benchmarkDraftFixtureId,
      revisionId: "benchmark-authoring-revision-cccccccccccccccccccccccccccccccc",
      documentFingerprint: `sha256:${"9".repeat(64)}`,
      suggestedSplit: "next",
    });
    expect(reconciled).toMatchObject({
      split: "next",
      taskIds: [],
      agentRevisions: [],
      validationResult: null,
      dryRunResult: null,
    });
  });
});
