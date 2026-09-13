import { describe, expect, it } from "vitest";
import { resolveStudioRouteContext, resolveStudioRouteTrail, STUDIO_GLOBAL_DESTINATIONS } from "./studioNavigation";

describe("studio product navigation", () => {
  it("keeps five stable product destinations", () => {
    expect(STUDIO_GLOBAL_DESTINATIONS.map((item) => item.id)).toEqual([
      "home",
      "agents",
      "experiments",
      "runs",
      "settings",
    ]);
  });

  it.each([
    ["/", "home", null],
    ["/builder", "agents", "agent"],
    ["/agents/agent-1/design", "agents", "agent"],
    ["/agents/agent-1/run", "agents", "agent"],
    ["/benchmarks", "experiments", "benchmark"],
    ["/benchmark-authoring", "experiments", "benchmark"],
    ["/experiments/new", "experiments", "experiment"],
    ["/experiments/experiment-1", "experiments", "experiment"],
    ["/experiments", "runs", "experiment"],
    ["/history", "runs", "run"],
    ["/runs/run-1/replay", "runs", "run"],
    ["/settings", "settings", "settings"],
  ] as const)("maps %s to %s", (path, destination, objectKind) => {
    expect(resolveStudioRouteContext(path)).toEqual({ destination, objectKind });
  });

  it("describes deep workbenches without copying raw route identities", () => {
    const trail = resolveStudioRouteTrail("/agents/agent-secret-identity/design");
    expect(trail).toEqual({ domainLabel: "Agents", contextLabel: "Agent 设计" });
    expect(JSON.stringify(trail)).not.toContain("agent-secret-identity");
    expect(resolveStudioRouteTrail("/history")).toBeNull();
  });
});
