import type { FlowStudioCardDefinition } from "./types";

export const plannerFlowCardDefinition = {
  id: "planner",
  group: "core",
  label: "Planner",
  desc: "The Planner.",
  icon: "📋",
  registrySlotId: "planner",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    { role: "task", portName: "Task Input", portKind: "input", dataTypes: ["task_input"], slot: 0.5 },
    { role: "plan", portName: "Plan", portKind: "output", dataTypes: ["plan_result"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
