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
    { role: "in_shot", portName: "Screenshot", portKind: "input", dataTypes: ["screenshot"], slot: 0.5 },
    { role: "out_perc", portName: "Perception Result", portKind: "output", dataTypes: ["perceptionResult"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
