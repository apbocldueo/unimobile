import type { FlowStudioCardDefinition } from "./types";

export const memoryFlowCardDefinition = {
  id: "memory",
  group: "core",
  label: "Memory",
  desc: "The Memory Hub.",
  icon: "🧠",
  registrySlotId: "memory",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    {
      role: "write",
      portName: "Context Input",
      portKind: "input",
      dataTypes: ["task_input", "plan_result", "action", "action_result", "verifier_result"],
      slot: 0.5,
    },
    { role: "context", portName: "Memory Context", portKind: "output", dataTypes: ["memory_context"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
