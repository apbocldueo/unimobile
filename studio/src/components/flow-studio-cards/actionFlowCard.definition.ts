import type { FlowStudioCardDefinition } from "./types";

export const actionFlowCardDefinition = {
  id: "action",
  group: "core",
  label: "Action",
  desc: "Execute device action.",
  icon: "🎮",
  canvasPresentation: "studioPalette",
  portBlueprints: [{ role: "in_action", portName: "Action Input", portKind: "input", dataTypes: ["action"], slot: 0.5 }],
} satisfies FlowStudioCardDefinition;
