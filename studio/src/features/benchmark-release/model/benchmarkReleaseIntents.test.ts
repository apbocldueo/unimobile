import { describe, expect, it } from "vitest";
import { benchmarkReleaseFreezeGate } from "../ui/BenchmarkReleaseView";
import { prepareBenchmarkReleaseIntent } from "./benchmarkReleaseIntents";

const cleanGate = {
  dirty: false,
  hasBufferError: false,
  hasUnappliedBuffer: false,
  baselineRevisionId: "revision-one",
  queryCurrentRevisionId: "revision-one",
  conflictRevisionId: null,
  remoteMayBeNewer: false,
  peerPending: false,
};

describe("Benchmark release local intent", () => {
  it("reuses an uncertain command only for unchanged operation and target", () => {
    const createIdentity = viIdentity("release-one", "release-two");
    const first = prepareBenchmarkReleaseIntent(null, {
      operation: "publish",
      draftId: "draft-one",
      targetId: "package-one",
    }, createIdentity);
    const retry = prepareBenchmarkReleaseIntent(first, {
      operation: "publish",
      draftId: "draft-one",
      targetId: "package-one",
    }, createIdentity);
    const changed = prepareBenchmarkReleaseIntent(first, {
      operation: "export",
      draftId: "draft-one",
      targetId: "package-one",
    }, createIdentity);
    expect(retry).toBe(first);
    expect(changed.command.clientRequestId).toBe("release-two");
  });

  it("gates Freeze on one clean saved exact-current baseline", () => {
    expect(benchmarkReleaseFreezeGate(cleanGate).allowed).toBe(true);
    expect(benchmarkReleaseFreezeGate({ ...cleanGate, dirty: true }).allowed).toBe(false);
    expect(benchmarkReleaseFreezeGate({
      ...cleanGate,
      baselineRevisionId: "revision-old",
    }).allowed).toBe(false);
    expect(benchmarkReleaseFreezeGate({
      ...cleanGate,
      peerPending: true,
    }).allowed).toBe(false);
  });
});

/** Return stable identities in call order for intent retry tests. */
function viIdentity(...values: string[]): () => string {
  let index = 0;
  return () => values[index++] ?? "release-overflow";
}
