import type { FlowStudioCardDefinition } from "./types";

export const inputFlowCardDefinition = {
  id: "input",
  group: "io",
  label: "Input",
  desc: "Task input",
  icon: "📥",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    { role: "task", portName: "Task Input", portKind: "output", dataTypes: ["task_input"], slot: 0.35 },
    { role: "observation", portName: "Device Observation", portKind: "output", dataTypes: ["device_observation"], slot: 0.65 },
  ],
} satisfies FlowStudioCardDefinition;
