import { describe, expect, it } from "vitest";
import { resolveStudioRouteContext, resolveStudioRouteTrail, STUDIO_GLOBAL_DESTINATIONS } from "./studioNavigation";

describe("studio product navigation", () => {
  it("keeps four personal product destinations", () => {
    expect(STUDIO_GLOBAL_DESTINATIONS.map((item) => item.id)).toEqual([
      "agents",
      "runs",
      "experiments",
      "settings",
    ]);
  });

  it.each([
    ["/", "home", null],
    ["/workspace", "agents", "agent"],
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
    expect(trail).toEqual({ domainLabel: "我的 Agents", contextLabel: "Agent 设计" });
    expect(JSON.stringify(trail)).not.toContain("agent-secret-identity");
    expect(resolveStudioRouteTrail("/history")).toBeNull();
  });
});
