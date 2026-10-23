import { uiText } from "@/shared/i18n";
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
  { id: "agents", /** Read this static UI label in the selected language. */ get label() { return uiText("我的 Agents"); }, path: "/agents", icon: "agents" },
  { id: "runs", /** Read this static UI label in the selected language. */ get label() { return uiText("运行记录"); }, path: "/history", icon: "runs" },
  { id: "experiments", /** Read this static UI label in the selected language. */ get label() { return uiText("评测"); }, path: "/benchmarks", icon: "experiments" },
  { id: "settings", /** Read this static UI label in the selected language. */ get label() { return uiText("设置"); }, path: "/settings", icon: "settings" },
] as const;

/** Resolve one route to its product domain without changing resource identity. */
export function resolveStudioRouteContext(pathname: string): StudioRouteContext {
  if (pathname === "/") return { destination: "home", objectKind: null };
  if (pathname === "/agents" || pathname === "/workspace" || pathname === "/builder" || pathname.startsWith("/agents/")) {
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
    agentLibrary: uiText("我的 Agents"),
    design: uiText("设计"),
    run: uiText("运行"),
    runs: uiText("运行记录"),
  }[term];
}

/** Describe a deep route with safe product context and no raw resource identity. */
export function resolveStudioRouteTrail(pathname: string): StudioRouteTrail | null {
  if (pathname.startsWith("/agents/") && pathname.endsWith("/design")) {
    return { domainLabel: uiText("我的 Agents"), contextLabel: uiText("Agent 设计") };
  }
  if (pathname.startsWith("/agents/") && pathname.endsWith("/run")) {
    return { domainLabel: uiText("我的 Agents"), contextLabel: uiText("Agent 运行") };
  }
  if (pathname.startsWith("/agents/") && pathname.endsWith("/runs")) {
    return { domainLabel: uiText("我的 Agents"), contextLabel: uiText("Agent 运行记录") };
  }
  if (pathname.startsWith("/runs/") && pathname.endsWith("/replay")) {
    return { domainLabel: uiText("运行记录"), contextLabel: uiText("只读 Replay") };
  }
  if (pathname === "/experiments/new") {
    return { domainLabel: uiText("评测"), contextLabel: uiText("新建 Experiment") };
  }
  if (pathname.startsWith("/experiments/") && pathname.endsWith("/report")) {
    return { domainLabel: uiText("评测"), contextLabel: uiText("Experiment 报告") };
  }
  if (pathname.startsWith("/experiments/")) {
    return { domainLabel: uiText("评测"), contextLabel: "Experiment Monitor" };
  }
  if (pathname.startsWith("/benchmark-authoring") || pathname.startsWith("/benchmark-drafts/")) {
    return { domainLabel: uiText("评测"), contextLabel: uiText("Benchmark 高级能力") };
  }
  if (pathname.startsWith("/benchmarks/")) {
    return { domainLabel: uiText("评测"), contextLabel: uiText("Benchmark 定义") };
  }
  return null;
}
