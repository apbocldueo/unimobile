export type StudioGlobalDestinationId =
  | "home"
  | "agents"
  | "experiments"
  | "runs"
  | "settings";

export type StudioGlobalDestination = Readonly<{
  id: StudioGlobalDestinationId;
  label: string;
  path: string;
  icon: "home" | "agents" | "experiments" | "runs" | "settings";
}>;

export type StudioRouteContext = Readonly<{
  destination: StudioGlobalDestinationId;
  objectKind: "agent" | "benchmark" | "experiment" | "run" | "settings" | null;
}>;

export type StudioRouteTrail = Readonly<{
  domainLabel: string;
  contextLabel: string;
}>;

/** Stable product navigation ordered by user objects and research lifecycle. */
export const STUDIO_GLOBAL_DESTINATIONS: readonly StudioGlobalDestination[] = [
  { id: "home", label: "首页", path: "/", icon: "home" },
  { id: "agents", label: "Agents", path: "/agents", icon: "agents" },
  { id: "experiments", label: "Experiments", path: "/benchmarks", icon: "experiments" },
  { id: "runs", label: "Runs", path: "/history", icon: "runs" },
  { id: "settings", label: "设置", path: "/settings", icon: "settings" },
] as const;

/** Resolve one route to its product domain without changing resource identity. */
export function resolveStudioRouteContext(pathname: string): StudioRouteContext {
  if (pathname === "/") return { destination: "home", objectKind: null };
  if (pathname === "/agents" || pathname === "/builder" || pathname.startsWith("/agents/")) {
    return { destination: "agents", objectKind: "agent" };
  }
  if (pathname.startsWith("/runs/") || pathname.startsWith("/history")) {
    return { destination: "runs", objectKind: "run" };
  }
  if (pathname === "/experiments" || pathname.startsWith("/experiments/")) {
    return pathname === "/experiments"
      ? { destination: "runs", objectKind: "experiment" }
      : { destination: "experiments", objectKind: "experiment" };
  }
  if (pathname.startsWith("/benchmark")) {
    return { destination: "experiments", objectKind: "benchmark" };
  }
  if (pathname.startsWith("/settings")) {
    return { destination: "settings", objectKind: "settings" };
  }
  return { destination: "home", objectKind: null };
}

/** Return the stable user-facing term for one previously inconsistent label. */
export function studioVocabulary(term: "agentLibrary" | "design" | "run" | "runs"): string {
  return {
    agentLibrary: "Agents",
    design: "设计",
    run: "运行",
    runs: "运行记录",
  }[term];
}

/** Describe a deep route with safe product context and no raw resource identity. */
export function resolveStudioRouteTrail(pathname: string): StudioRouteTrail | null {
  if (pathname.startsWith("/agents/") && pathname.endsWith("/design")) {
    return { domainLabel: "Agents", contextLabel: "Agent 设计" };
  }
  if (pathname.startsWith("/agents/") && pathname.endsWith("/run")) {
    return { domainLabel: "Agents", contextLabel: "Agent 运行" };
  }
  if (pathname.startsWith("/agents/") && pathname.endsWith("/runs")) {
    return { domainLabel: "Agents", contextLabel: "Agent 运行记录" };
  }
  if (pathname.startsWith("/runs/") && pathname.endsWith("/replay")) {
    return { domainLabel: "Runs", contextLabel: "只读 Replay" };
  }
  if (pathname === "/experiments/new") {
    return { domainLabel: "Experiments", contextLabel: "新建 Experiment" };
  }
  if (pathname.startsWith("/experiments/") && pathname.endsWith("/report")) {
    return { domainLabel: "Experiments", contextLabel: "Experiment 报告" };
  }
  if (pathname.startsWith("/experiments/")) {
    return { domainLabel: "Experiments", contextLabel: "Experiment Monitor" };
  }
  if (pathname.startsWith("/benchmark-authoring") || pathname.startsWith("/benchmark-drafts/")) {
    return { domainLabel: "Experiments", contextLabel: "Benchmark 高级能力" };
  }
  if (pathname.startsWith("/benchmarks/")) {
    return { domainLabel: "Experiments", contextLabel: "Benchmark 定义" };
  }
  return null;
}
