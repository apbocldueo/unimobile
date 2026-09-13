import { afterEach, describe, expect, it, vi } from "vitest";
import { loadRunArtifactText, runArtifactUrl } from "@/entities/artifact";

const runId = `run-${"a".repeat(32)}`;
const artifactId = `artifact-${"b".repeat(32)}`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("live Run artifact API", () => {
  it("builds only run-scoped opaque artifact URLs", () => {
    expect(runArtifactUrl(runId, artifactId)).toBe(
      `/zhixing-studio/api/studio/runs/${runId}/artifacts/${artifactId}`,
    );
    expect(() => runArtifactUrl(runId, "/tmp/model.txt")).toThrow(/opaque/);
    expect(() => runArtifactUrl("../other-run", artifactId)).toThrow(/opaque/);
  });

  it("loads bounded model text and preserves HTTP error codes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response("model response", {
          status: 200,
          headers: { "Content-Length": "14" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: "studio.run.artifact_not_found",
              message: "artifact is unavailable",
            },
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    await expect(loadRunArtifactText(runId, artifactId)).resolves.toBe(
      "model response",
    );
    await expect(loadRunArtifactText(runId, artifactId)).rejects.toMatchObject({
      status: 404,
      code: "studio.run.artifact_not_found",
    });
  });
});
