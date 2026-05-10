import type { FlowStudioCardDefinition } from "./types";

export const inputFlowCardDefinition = {
  id: "input",
  group: "io",
  label: "Input",
  desc: "Task input",
  icon: "📥",
  canvasPresentation: "studioPalette",
  portBlueprints: [{ role: "out_task", portName: "Task Output", portKind: "output", dataTypes: ["taskInput"], slot: 0.5 }],
} satisfies FlowStudioCardDefinition;
