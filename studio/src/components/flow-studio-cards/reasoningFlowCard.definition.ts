import type { FlowStudioCardDefinition } from "./types";

export const reasoningFlowCardDefinition = {
  id: "reasoning",
  group: "core",
  label: "Reasoning",
  desc: "The Decision Core.",
  icon: "⚡",
  registrySlotId: "reasoning",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    {
      role: "in_plan",
      portName: "Plan",
      portKind: "input",
      dataTypes: ["plan", "verifiedPlan"],
      slot: 1 / 6,
    },
    {
      role: "in_perc",
      portName: "Perception Result",
      portKind: "input",
      dataTypes: ["perceptionResult"],
      slot: 3 / 6,
    },
    {
      role: "in_mem",
      portName: "Memory Context",
      portKind: "input",
      dataTypes: ["memoryContext"],
      slot: 5 / 6,
    },
    { role: "out_action", portName: "Action", portKind: "output", dataTypes: ["action"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
