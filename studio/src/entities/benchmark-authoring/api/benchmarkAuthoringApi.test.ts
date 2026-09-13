import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createBenchmarkDraft,
  benchmarkDryRunResultFixture,
  benchmarkContractProfilePageFixture,
  benchmarkContractTestResultFixture,
  benchmarkValidationResultFixture,
  dryRunBenchmarkDraft,
  getBenchmarkDraftRevision,
  headBenchmarkAuthoringResource,
  listBenchmarkDrafts,
  listBenchmarkContractTestProfiles,
  removeBenchmarkAuthoringResource,
  replaceBenchmarkAuthoringResource,
  runBenchmarkContractTests,
  saveBenchmarkDraftRevision,
  uploadBenchmarkAuthoringResource,
  validateBenchmarkDraft,
} from "@/entities/benchmark-authoring";
import { StudioApiError } from "@/shared/api";
import {
  benchmarkAuthoringContentCommandFixture,
  benchmarkAuthoringDocumentFixture,
  benchmarkDraftCommandFixture,
  benchmarkDraftFixtureId,
  benchmarkDraftPageFixture,
  benchmarkRevisionFixtureId,
} from "../testing/benchmarkAuthoring.fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Build one JSON HTTP response for the shared API transport. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Benchmark authoring API", () => {
  it("maps bounded pages and exact draft-scoped revisions", async () => {
    const command = benchmarkDraftCommandFixture();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(benchmarkDraftPageFixture()))
      .mockResolvedValueOnce(jsonResponse(command.revision));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    await listBenchmarkDrafts(
      { limit: 10, cursor: "opaque-next" },
      controller.signal,
    );
    await getBenchmarkDraftRevision(
      benchmarkDraftFixtureId,
      benchmarkRevisionFixtureId,
    );
    expect(fetchMock.mock.calls[0]?.[0]).toContain(
      "limit=10&cursor=opaque-next",
    );
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({ signal: controller.signal }),
    );
    expect(fetchMock.mock.calls[1]?.[0]).toContain(
      `${benchmarkDraftFixtureId}/revisions/${benchmarkRevisionFixtureId}`,
    );
  });

  it("keeps an unchanged create command body stable for retry", async () => {
    const command = benchmarkDraftCommandFixture();
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse(command)),
    );
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      schemaVersion: 1 as const,
      clientRequestId: "benchmark-draft-create-fixture",
      name: "Fixture",
      source: {
        kind: "template" as const,
        template: "minimal" as const,
        publisher: "fixture",
        packageName: "authoring",
        version: "0.1.0",
      },
    };
    await createBenchmarkDraft(input);
    await createBenchmarkDraft(input);
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(
      fetchMock.mock.calls[1]?.[1]?.body,
    );
  });

  it("preserves a safe current revision fact on save conflict", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            schemaVersion: 1,
            error: {
              code: "benchmark.authoring.revision_conflict",
              message: "Current revision changed",
              currentRevisionId: benchmarkRevisionFixtureId,
            },
          },
          409,
        ),
      ),
    );
    await expect(
      saveBenchmarkDraftRevision(benchmarkDraftFixtureId, {
        schemaVersion: 1,
        clientRequestId: "benchmark-save-fixture",
        baseRevisionId: benchmarkRevisionFixtureId,
        document: benchmarkAuthoringDocumentFixture(),
      }),
    ).rejects.toMatchObject({
      status: 409,
      code: "benchmark.authoring.revision_conflict",
      currentRevisionId: benchmarkRevisionFixtureId,
    } satisfies Partial<StudioApiError>);
  });

  it("uses exact owner-scoped raw routes for upload, replace, and remove", async () => {
    const uploadResult = benchmarkAuthoringContentCommandFixture("upload");
    const replaceResult = benchmarkAuthoringContentCommandFixture("replace");
    const removeResult = benchmarkAuthoringContentCommandFixture("remove");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(uploadResult, 201))
      .mockResolvedValueOnce(jsonResponse(replaceResult, 201))
      .mockResolvedValueOnce(jsonResponse(removeResult, 201));
    vi.stubGlobal("fetch", fetchMock);
    const uploadBody = new File(["asset"], "asset.txt", { type: "text/plain" });
    const replaceBody = new File(["new"], "replacement.txt", {
      type: "text/plain",
    });

    await uploadBenchmarkAuthoringResource({
      draftId: benchmarkDraftFixtureId,
      baseRevisionId: benchmarkRevisionFixtureId,
      clientRequestId: "upload-request",
      resourceId: "new asset",
      kind: "asset",
      path: "assets/fixture name.txt",
      mediaType: "text/plain",
      body: uploadBody,
    });
    await replaceBenchmarkAuthoringResource({
      draftId: benchmarkDraftFixtureId,
      baseRevisionId: benchmarkRevisionFixtureId,
      clientRequestId: "replace-request",
      resourceId: "fixture-asset",
      mediaType: "text/plain",
      body: replaceBody,
    });
    await removeBenchmarkAuthoringResource({
      draftId: benchmarkDraftFixtureId,
      baseRevisionId: benchmarkRevisionFixtureId,
      clientRequestId: "remove-request",
      resourceId: "fixture-asset",
    });

    const uploadUrl = String(fetchMock.mock.calls[0]?.[0]);
    const uploadInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(uploadUrl).toContain("/resources/new%20asset/upload?");
    expect(uploadUrl).toContain("path=assets%2Ffixture+name.txt");
    expect(uploadUrl).not.toContain("contentIdentity");
    expect(uploadInit.body).toBe(uploadBody);
    expect(new Headers(uploadInit.headers).has("Content-Length")).toBe(false);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ body: replaceBody });
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({
      method: "POST",
      body: undefined,
    });
  });

  it("checks exact resource availability through HEAD metadata", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.method).toBe("HEAD");
      return new Response(null, {
        status: 200,
        headers: {
          "Content-Type": "image/png",
          "Content-Length": "128",
          "Content-Disposition": 'attachment; filename="fixture-asset"',
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      headBenchmarkAuthoringResource({
        draftId: benchmarkDraftFixtureId,
        revisionId: benchmarkRevisionFixtureId,
        resourceId: "fixture-asset",
        mediaType: "image/png",
        size: 128,
      }),
    ).resolves.toMatchObject({ filename: "fixture-asset" });
    const path = String(fetchMock.mock.calls[0]?.[0]);
    expect(path).toContain(
      `${benchmarkDraftFixtureId}/revisions/${benchmarkRevisionFixtureId}/resources/fixture-asset/content`,
    );
    expect(path).not.toContain("benchmark-content-");
  });

  it("posts exact revision-bound validation and dry-run bodies", async () => {
    const validation = benchmarkValidationResultFixture();
    const dryRun = benchmarkDryRunResultFixture();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(validation))
      .mockResolvedValueOnce(jsonResponse(dryRun));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await validateBenchmarkDraft({
      draftId: validation.draftId,
      request: {
        schemaVersion: 1,
        revisionId: validation.revisionId,
        split: validation.split,
      },
      signal: controller.signal,
    });
    await dryRunBenchmarkDraft({
      draftId: dryRun.draftId,
      request: {
        schemaVersion: 1,
        revisionId: dryRun.revisionId,
        split: dryRun.split,
        taskIds: [],
        agentRevisions: dryRun.agentRevisions.map((item) => ({
          agentId: item.agentId,
          revisionId: item.revisionId,
        })),
      },
    });

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      `${validation.draftId}/validate`,
    );
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({
        schemaVersion: 1,
        revisionId: validation.revisionId,
        split: validation.split,
      }),
      signal: controller.signal,
    });
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(
      `${dryRun.draftId}/dry-run`,
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      schemaVersion: 1,
      revisionId: dryRun.revisionId,
      split: dryRun.split,
      taskIds: [],
      agentRevisions: dryRun.agentRevisions.map((item) => ({
        agentId: item.agentId,
        revisionId: item.revisionId,
      })),
    });
  });

  it("loads metadata-only fixture profiles and posts one exact transient Contract Test", async () => {
    const profiles = benchmarkContractProfilePageFixture();
    const result = benchmarkContractTestResultFixture();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(profiles))
      .mockResolvedValueOnce(jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await listBenchmarkContractTestProfiles(controller.signal);
    await runBenchmarkContractTests({
      draftId: result.draftId,
      request: {
        schemaVersion: 1,
        revisionId: result.revisionId,
        split: result.split,
        seed: result.seed,
        fixtureProfileId: result.profile.profileId,
      },
      signal: controller.signal,
    });

    expect(fetchMock.mock.calls[0]?.[0]).toContain("/contract-test-profiles");
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({ signal: controller.signal }),
    );
    expect(fetchMock.mock.calls[1]?.[0]).toContain(
      `${result.draftId}/contract-tests`,
    );
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({
        schemaVersion: 1,
        revisionId: result.revisionId,
        split: result.split,
        seed: result.seed,
        fixtureProfileId: result.profile.profileId,
      }),
      signal: controller.signal,
    });
  });

  it.each([400, 404, 409, 413, 503])(
    "preserves bounded analysis HTTP failure %s",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          jsonResponse(
            {
              schemaVersion: 1,
              error: {
                code: `benchmark.analysis.http_${status}`,
                message: "Safe analysis failure",
                ...(status === 409
                  ? { currentRevisionId: benchmarkRevisionFixtureId }
                  : {}),
              },
            },
            status,
          ),
        ),
      );
      await expect(
        validateBenchmarkDraft({
          draftId: benchmarkDraftFixtureId,
          request: {
            schemaVersion: 1,
            revisionId: benchmarkRevisionFixtureId,
            split: "test",
          },
        }),
      ).rejects.toMatchObject({
        status,
        ...(status === 409
          ? { currentRevisionId: benchmarkRevisionFixtureId }
          : {}),
      } satisfies Partial<StudioApiError>);
    },
  );

  it.each([400, 404, 409, 413, 503])(
    "preserves bounded Contract Test HTTP failure %s",
    async (status) => {
      const result = benchmarkContractTestResultFixture();
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          jsonResponse(
            {
              schemaVersion: 1,
              error: {
                code: `benchmark.authoring.contract_test_http_${status}`,
                message: "Safe Contract Test failure",
                ...(status === 409
                  ? { currentRevisionId: result.revisionId }
                  : {}),
              },
            },
            status,
          ),
        ),
      );
      await expect(
        runBenchmarkContractTests({
          draftId: result.draftId,
          request: {
            schemaVersion: 1,
            revisionId: result.revisionId,
            split: result.split,
            seed: result.seed,
            fixtureProfileId: result.profile.profileId,
          },
        }),
      ).rejects.toMatchObject({
        status,
        ...(status === 409
          ? { currentRevisionId: result.revisionId }
          : {}),
      } satisfies Partial<StudioApiError>);
    },
  );
});
