import type { FlowStudioCardDefinition } from "./types";

export const ifElseFlowCardDefinition = {
  id: "ifelse",
  group: "flow",
  label: "If-Else",
  desc: "用于判断条件，分流执行不同流程分支",
  icon: "🔀",
  canvasPresentation: "custom",
  portBlueprints: [
    { role: "value", portName: "Condition Input", portKind: "input", dataTypes: ["verifier_result", "action_result"], slot: 0.5 },
    { role: "true", portName: "True", portKind: "output", dataTypes: ["control"], slot: 0.38 },
    { role: "false", portName: "False", portKind: "output", dataTypes: ["control"], slot: 0.62 },
  ],
} satisfies FlowStudioCardDefinition;
