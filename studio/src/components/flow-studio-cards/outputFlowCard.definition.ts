import type { FlowStudioCardDefinition } from "./types";

export const outputFlowCardDefinition = {
  id: "output",
  group: "io",
  label: "Output",
  desc: "Device output",
  icon: "📤",
  canvasPresentation: "studioPalette",
  portBlueprints: [{ role: "in_action", portName: "Action Input", portKind: "input", dataTypes: ["action"], slot: 0.5 }],
} satisfies FlowStudioCardDefinition;
