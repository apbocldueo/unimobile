import { describe, expect, it } from "vitest";
import { exactRevisionReadinessQueryOptions } from "./runtimeReadiness.queries";

describe("exact revision readiness query", () => {
  it("actively rechecks a previously blocked Run Bar", () => {
    const options = exactRevisionReadinessQueryOptions(
      "agent-1",
      "revision-1",
      "local-android",
    );

    expect(options.refetchInterval).toBe(3_000);
    expect(options.refetchOnMount).toBe("always");
    expect(options.refetchOnWindowFocus).toBe("always");
  });
});
