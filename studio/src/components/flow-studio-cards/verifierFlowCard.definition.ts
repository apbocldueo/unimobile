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
    { role: "in_plan", portName: "Plan", portKind: "input", dataTypes: ["plan"], slot: 1 / 6 },
    { role: "in_action", portName: "Previous Action", portKind: "input", dataTypes: ["action"], slot: 3 / 6 },
    { role: "in_shot", portName: "Screenshot", portKind: "input", dataTypes: ["screenshot"], slot: 5 / 6 },
    { role: "out_verified", portName: "Verified Plan", portKind: "output", dataTypes: ["verifiedPlan"], slot: 0.5 },
  ],
} satisfies FlowStudioCardDefinition;
