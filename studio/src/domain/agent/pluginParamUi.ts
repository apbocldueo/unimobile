import { useStudioAgentRegistryStore } from "@/stores/studioAgentRegistryStore";

/** 画布卡片内超参数 UI 定义（与真实 YAML 契约可对齐）。 */

export type ParamFieldDef =
  | {
      id: string;
      label: string;
      hint?: string;
      kind: "select";
      options: { value: string; label: string }[];
      defaultValue: string;
    }
  | {
      id: string;
      label: string;
      hint?: string;
      kind: "text";
      defaultValue: string;
      placeholder?: string;
    }
  | {
      id: string;
      label: string;
      hint?: string;
      kind: "number";
      defaultValue: number;
      min?: number;
      max?: number;
    };

export type ParamGroupDef = {
  id: string;
  title: string;
  /** 高级参数分组在右侧面板默认折叠 */
  tier?: "core" | "advanced";
  fields: ParamFieldDef[];
};

export function validateParamField(field: ParamFieldDef, raw: string): string | null {
  if (field.kind === "select") return null;
  if (field.kind === "number") {
    if (raw.trim() === "") return "请输入有效数字";
    const n = Number(raw);
    if (Number.isNaN(n)) return "请输入有效数字";
    if (field.min !== undefined && n < field.min) return "参数低于合理范围";
    if (field.max !== undefined && n > field.max) return "参数超出合理范围";
  }
  return null;
}

export const PLUGIN_PARAM_GROUPS: Record<string, ParamGroupDef[]> = {
  som: [
    {
      id: "model",
      title: "模型选择",
      tier: "core",
      fields: [
        {
          id: "dl_backend",
          label: "深度学习模型",
          hint: "选择 SoM 对应的深度学习模型，不同模型适配不同场景与算力。",
          kind: "select",
          defaultValue: "resnet_tiny",
          options: [
            { value: "resnet_tiny", label: "ResNet-Tiny（轻量）" },
            { value: "vit_small", label: "ViT-Small（通用）" },
            { value: "custom_onnx", label: "自定义 ONNX" },
          ],
        },
      ],
    },
    {
      id: "core",
      title: "核心参数",
      tier: "core",
      fields: [
        {
          id: "grid_size",
          label: "网格尺寸",
          kind: "select",
          defaultValue: "16",
          options: [
            { value: "8", label: "8×8" },
            { value: "16", label: "16×16" },
            { value: "32", label: "32×32" },
          ],
        },
      ],
    },
    {
      id: "advanced",
      title: "高级参数",
      tier: "advanced",
      fields: [
        {
          id: "timeout_ms",
          label: "推理超时 (ms)",
          kind: "number",
          defaultValue: 8000,
          min: 1000,
          max: 60000,
        },
      ],
    },
  ],
  screenshot: [
    {
      id: "capture",
      title: "模型选择",
      tier: "core",
      fields: [
        {
          id: "capture_mode",
          label: "截图模式",
          hint: "全屏截取适用于整图对齐；活动窗口适合单应用调试。",
          kind: "select",
          defaultValue: "full_screen",
          options: [
            { value: "full_screen", label: "全屏" },
            { value: "window", label: "活动窗口" },
          ],
        },
      ],
    },
    {
      id: "encode",
      title: "核心参数",
      tier: "core",
      fields: [
        {
          id: "jpeg_quality",
          label: "JPEG 质量",
          kind: "number",
          defaultValue: 85,
          min: 60,
          max: 100,
        },
      ],
    },
    {
      id: "advanced",
      title: "高级参数",
      tier: "advanced",
      fields: [
        {
          id: "prefix",
          label: "文件前缀",
          kind: "text",
          defaultValue: "cap_",
          placeholder: "cap_",
        },
      ],
    },
  ],
  grid_perception: [
    {
      id: "core",
      title: "核心参数",
      tier: "core",
      fields: [
        {
          id: "cell_weight",
          label: "宫格权重",
          hint: "控制九宫格各格在融合时的相对权重。",
          kind: "select",
          defaultValue: "uniform",
          options: [
            { value: "uniform", label: "均匀" },
            { value: "center", label: "中心加强" },
          ],
        },
      ],
    },
  ],
};

export function getPluginParamGroups(pluginId: string): ParamGroupDef[] {
  const remote = useStudioAgentRegistryStore.getState().data?.paramCatalog?.[pluginId];
  if (remote?.length) return remote as ParamGroupDef[];
  return PLUGIN_PARAM_GROUPS[pluginId] ?? [];
}

export function buildParamValueErrors(pluginId: string, mergedParams: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const g of getPluginParamGroups(pluginId)) {
    for (const f of g.fields) {
      const m = validateParamField(f, mergedParams[f.id] ?? "");
      if (m) out[f.id] = m;
    }
  }
  return out;
}

/** 卡片内精简预览：其余字段在右侧属性面板编辑。 */
const CARD_PREVIEW_PARAM_IDS: Record<string, string[]> = {
  som: ["dl_backend", "grid_size"],
  screenshot: ["capture_mode", "jpeg_quality"],
  grid_perception: ["cell_weight"],
};

export function getPluginParamGroupsCardPreview(pluginId: string): ParamGroupDef[] {
  const full = getPluginParamGroups(pluginId);
  const ids = CARD_PREVIEW_PARAM_IDS[pluginId];
  if (!ids) return full;
  return full
    .map((g) => ({
      ...g,
      fields: g.fields.filter((f) => ids.includes(f.id)),
    }))
    .filter((g) => g.fields.length > 0);
}

/** 卡片上一行核心参数摘要（与预览字段一致）。 */
export function formatParamBriefLine(pluginId: string, merged: Record<string, string>): string {
  const preview = getPluginParamGroupsCardPreview(pluginId);
  const parts: string[] = [];
  for (const g of preview) {
    for (const f of g.fields) {
      const v = merged[f.id] ?? "";
      let display = v;
      if (f.kind === "select") {
        const opt = f.options.find((o) => o.value === v);
        if (opt) display = opt.label;
      }
      parts.push(`${f.label}：${display}`);
    }
  }
  return parts.slice(0, 2).join(" · ") || "请在右侧面板配置参数";
}

export function getDefaultSlotParamValues(pluginId: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const g of getPluginParamGroups(pluginId)) {
    for (const f of g.fields) {
      if (f.kind === "number") out[f.id] = String(f.defaultValue);
      else out[f.id] = f.defaultValue;
    }
  }
  return out;
}
