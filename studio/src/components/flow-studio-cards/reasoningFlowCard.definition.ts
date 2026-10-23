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
      role: "plan",
      portName: "Plan",
      portKind: "input",
      dataTypes: ["plan_result"],
      slot: 1 / 6,
    },
    {
      role: "perception",
      portName: "Perception Result",
      portKind: "input",
      dataTypes: ["perception_result"],
      slot: 3 / 6,
    },
    {
      role: "memory",
      portName: "Memory Context",
      portKind: "input",
      dataTypes: ["memory_context"],
      slot: 5 / 6,
    },
    { role: "task", portName: "Task", portKind: "input", dataTypes: ["task_input"], slot: 0.1 },
    { role: "verification", portName: "Verification", portKind: "input", dataTypes: ["verifier_result"], slot: 0.9 },
    { role: "action", portName: "Action", portKind: "output", dataTypes: ["action"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
