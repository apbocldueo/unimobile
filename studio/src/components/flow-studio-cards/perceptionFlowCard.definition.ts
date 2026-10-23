import type { FlowStudioCardDefinition } from "./types";

export const perceptionFlowCardDefinition = {
  id: "perception",
  group: "core",
  label: "Perception",
  desc: "The Eye of the agent.",
  icon: "👁️",
  registrySlotId: "perception",
  canvasPresentation: "studioPalette",
  portBlueprints: [
    { role: "observation", portName: "Device Observation", portKind: "input", dataTypes: ["device_observation"], slot: 0.5 },
    { role: "perception", portName: "Perception Result", portKind: "output", dataTypes: ["perception_result"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
