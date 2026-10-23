import type { FlowStudioCardDefinition } from "./types";

export const actionFlowCardDefinition = {
  id: "action",
  group: "core",
  label: "Action",
  desc: "Execute device action.",
  icon: "🎮",
  registrySlotId: "action_executor",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    { role: "action", portName: "Action Input", portKind: "input", dataTypes: ["action"], slot: 0.4 },
    { role: "observation", portName: "Observation", portKind: "input", dataTypes: ["device_observation"], slot: 0.7 },
    { role: "result", portName: "Action Result", portKind: "output", dataTypes: ["action_result"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
