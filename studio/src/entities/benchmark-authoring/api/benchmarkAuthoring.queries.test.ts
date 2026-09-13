import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import {
  benchmarkAuthoringContentCommandFixture,
  benchmarkAuthoringKeys,
  benchmarkAuthoringRevisionFixture,
  benchmarkDraftDetailFixture,
  benchmarkLaterRevisionFixtureId,
  reconcileBenchmarkAuthoringContentResult,
} from "@/entities/benchmark-authoring";

/** Build a current detail that is newer than a historical retry response. */
function laterDraftDetail() {
  const initial = benchmarkDraftDetailFixture();
  const revision = {
    ...benchmarkAuthoringRevisionFixture("edit"),
    revisionId: benchmarkLaterRevisionFixtureId,
    ordinal: 3,
    parentRevisionId: initial.currentRevision.revisionId,
    createdAt: initial.currentRevision.createdAt + 2,
  };
  return {
    schemaVersion: 1 as const,
    draft: {
      ...initial.draft,
      currentRevisionId: revision.revisionId,
      updatedAt: revision.createdAt,
    },
    currentRevision: revision,
  };
}

describe("benchmark authoring content cache reconciliation", () => {
  it("seeds the exact revision and advances detail for an aligned result", async () => {
    const client = new QueryClient();
    const result = benchmarkAuthoringContentCommandFixture("upload");

    const outcome = await reconcileBenchmarkAuthoringContentResult(
      client,
      result,
    );

    expect(outcome.historicalRetry).toBe(false);
    expect(outcome.currentRevision.revisionId).toBe(result.revision.revisionId);
    expect(
      client.getQueryData(
        benchmarkAuthoringKeys.revision(
          result.draft.draftId,
          result.revision.revisionId,
        ),
      ),
    ).toEqual(result.revision);
    expect(
      client.getQueryData(benchmarkAuthoringKeys.detail(result.draft.draftId)),
    ).toMatchObject({
      draft: { currentRevisionId: result.revision.revisionId },
      currentRevision: { revisionId: result.revision.revisionId },
    });
  });

  it("keeps the exact historical revision but authoritatively refetches current", async () => {
    const client = new QueryClient();
    const result = benchmarkAuthoringContentCommandFixture("replace", true);
    const later = laterDraftDetail();
    client.setQueryData(
      benchmarkAuthoringKeys.detail(result.draft.draftId),
      benchmarkDraftDetailFixture(),
    );

    const outcome = await reconcileBenchmarkAuthoringContentResult(
      client,
      result,
      async () => later,
    );

    expect(outcome.historicalRetry).toBe(true);
    expect(outcome.currentRevision.revisionId).toBe(
      benchmarkLaterRevisionFixtureId,
    );
    expect(
      client.getQueryData(
        benchmarkAuthoringKeys.revision(
          result.draft.draftId,
          result.revision.revisionId,
        ),
      ),
    ).toEqual(result.revision);
    expect(
      client.getQueryData(benchmarkAuthoringKeys.detail(result.draft.draftId)),
    ).toEqual(later);
  });
});
