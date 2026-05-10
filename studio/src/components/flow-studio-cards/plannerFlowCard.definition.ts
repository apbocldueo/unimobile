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
    { role: "in_task", portName: "Task Input", portKind: "input", dataTypes: ["taskInput"], slot: 0.5 },
    { role: "out_plan", portName: "Plan", portKind: "output", dataTypes: ["plan"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
