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
      role: "in_ctx",
      portName: "Context Input",
      portKind: "input",
      dataTypes: ["plan", "perceptionResult", "action"],
      slot: 0.5,
    },
    { role: "out_mem", portName: "Memory Context", portKind: "output", dataTypes: ["memoryContext"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
