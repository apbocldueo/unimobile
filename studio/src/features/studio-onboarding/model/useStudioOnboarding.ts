import { useState } from "react";

const ONBOARDING_PREFERENCE_KEY = "zx-studio-onboarding-dismissed-v1";

export type StudioOnboardingPrerequisite =
  | "none"
  | "agent"
  | "valid_revision"
  | "runtime_ready"
  | "run"
  | "replay";

export type StudioOnboardingStep = Readonly<{
  id: "choose" | "design" | "run" | "inspect" | "replay";
  label: string;
  path: string;
  prerequisite: StudioOnboardingPrerequisite;
}>;

/** Formal presentation-only path whose prerequisites remain server-owned facts. */
export const STUDIO_ONBOARDING_STEPS: readonly StudioOnboardingStep[] = [
  { id: "choose", label: "选择或创建 Agent", path: "/agents", prerequisite: "none" },
  { id: "design", label: "设计并验证", path: "/agents", prerequisite: "agent" },
  { id: "run", label: "运行任务", path: "/agents", prerequisite: "runtime_ready" },
  { id: "inspect", label: "检查结果", path: "/history", prerequisite: "run" },
  { id: "replay", label: "Replay 与迭代", path: "/history", prerequisite: "replay" },
] as const;

/** Read the optional presentation preference without treating it as product truth. */
function readDismissedPreference(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(ONBOARDING_PREFERENCE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Manage only dismissal/reopen preference for the Studio golden-path guidance. */
export function useStudioOnboarding() {
  const [dismissed, setDismissed] = useState(readDismissedPreference);
  /** Persist only the optional visibility preference for this browser. */
  const persist = (value: boolean) => {
    setDismissed(value);
    try {
      window.localStorage.setItem(ONBOARDING_PREFERENCE_KEY, value ? "1" : "0");
    } catch {
      // A blocked preference store must not block any Studio workflow.
    }
  };
  return {
    dismissed,
    dismiss: () => persist(true),
    reopen: () => persist(false),
  } as const;
}
