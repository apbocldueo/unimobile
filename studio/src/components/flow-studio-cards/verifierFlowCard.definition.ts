import type { FlowStudioCardDefinition } from "./types";

export const verifierFlowCardDefinition = {
  id: "verifier",
  group: "core",
  label: "Verifier",
  desc: "The Quality Inspector.",
  icon: "✅",
  registrySlotId: "verifier",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    { role: "task", portName: "Task", portKind: "input", dataTypes: ["task_input"], slot: 1 / 7 },
    { role: "before", portName: "Before", portKind: "input", dataTypes: ["device_observation"], slot: 2 / 7 },
    { role: "after", portName: "After", portKind: "input", dataTypes: ["device_observation"], slot: 3 / 7 },
    { role: "action", portName: "Action", portKind: "input", dataTypes: ["action"], slot: 4 / 7 },
    { role: "action_result", portName: "Action Result", portKind: "input", dataTypes: ["action_result"], slot: 5 / 7 },
    { role: "result", portName: "Verifier Result", portKind: "output", dataTypes: ["verifier_result"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
