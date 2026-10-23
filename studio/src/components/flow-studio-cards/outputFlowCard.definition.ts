import type { FlowStudioCardDefinition } from "./types";

export const outputFlowCardDefinition = {
  id: "output",
  group: "io",
  label: "Output",
  desc: "Device output",
  icon: "📤",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    { role: "result", portName: "Result", portKind: "input", dataTypes: ["action_result", "run_result"], slot: 0.4 },
    { role: "control", portName: "Control", portKind: "input", dataTypes: ["control"], slot: 0.7 },
  ],
} satisfies FlowStudioCardDefinition;
