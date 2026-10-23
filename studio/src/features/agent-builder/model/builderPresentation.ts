import { uiText } from "@/shared/i18n";
import type { CapabilityFamily } from "@/entities/component-catalog";

/** Family-level guidance only: never substitutes for an implementation contract. */
export const capabilityPurpose: Record<CapabilityFamily, string> = {
  /** Read this static UI label in the selected language. */ get perception() { return uiText("理解当前屏幕，为后续决策提供感知信息。"); },
  /** Read this static UI label in the selected language. */ get planner() { return uiText("将任务组织为计划，为后续决策提供步骤。"); },
  /** Read this static UI label in the selected language. */ get reasoning() { return uiText("结合任务与上下文，选择下一步动作。"); },
  /** Read this static UI label in the selected language. */ get memory() { return uiText("保存与读取交互上下文，供后续步骤使用。"); },
  /** Read this static UI label in the selected language. */ get action_executor() { return uiText("通过正式设备边界执行请求的动作。"); },
  /** Read this static UI label in the selected language. */ get verifier() { return uiText("检查任务或动作相关证据，提供验证反馈；不等同于 Benchmark 评估。"); },
  /** Read this static UI label in the selected language. */ get grounder() { return uiText("将目标定位到可操作的屏幕位置。"); },
  /** Read this static UI label in the selected language. */ get tool() { return uiText("使用框架批准的独立工具能力；具体行为以所选实现合同为准。"); },
};
