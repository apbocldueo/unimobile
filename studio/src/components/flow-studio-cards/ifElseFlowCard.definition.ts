import type { FlowStudioCardDefinition } from "./types";
import { WILDCARD_FLOW_TYPE } from "@/modules/flow-graph/flowDataTypes";

export const ifElseFlowCardDefinition = {
  id: "ifelse",
  group: "flow",
  label: "If-Else",
  desc: "用于判断条件，分流执行不同流程分支",
  icon: "🔀",
  canvasPresentation: "custom",
  portBlueprints: [
    { role: "in_cond", portName: "Condition Input", portKind: "input", dataTypes: ["condition", "plan", "taskInput"], slot: 0.5 },
    { role: "out_true", portName: "True", portKind: "output", dataTypes: [WILDCARD_FLOW_TYPE], slot: 0.38 },
    { role: "out_false", portName: "False", portKind: "output", dataTypes: [WILDCARD_FLOW_TYPE], slot: 0.62 },
  ],
} satisfies FlowStudioCardDefinition;
