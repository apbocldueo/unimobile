/** 与 ``GET /studio/builder/agent-registry`` 对齐（由 ZhiXing 生成）。 */

/** 与 ``ParamFieldDef`` 同形，独立声明以免与 ``pluginParamUi`` 循环引用。 */
export type StudioRegistryParamFieldDTO =
  | {
      id: string;
      label: string;
      hint?: string | null;
      kind: "select";
      options: { value: string; label: string }[];
      defaultValue: string;
    }
  | {
      id: string;
      label: string;
      hint?: string | null;
      kind: "text";
      defaultValue: string;
      placeholder?: string;
    }
  | {
      id: string;
      label: string;
      hint?: string | null;
      kind: "number";
      defaultValue: number;
      min?: number;
      max?: number;
    };

export type StudioRegistryParamGroupDTO = {
  id: string;
  title: string;
  tier?: "core" | "advanced";
  fields: StudioRegistryParamFieldDTO[];
};

export type StudioAgentRegistrySlotDTO = {
  slotId: string;
  title: string;
  roleLabel: string;
  /** 与 ``zhixing.core.agent.interfaces`` 对应 Base* 的 ``_description`` 一致，由 ``agent-registry`` 下发 */
  baseDescription?: string;
};

export type StudioAgentRegistryPluginDTO = {
  id: string;
  namespace: string;
  className: string;
  title: string;
  description: string;
  paramGroups: StudioRegistryParamGroupDTO[];
};

export type StudioAgentRegistryModularDTO = {
  strategyId: "modular";
  backendPluginName: string;
  title: string;
  description: string;
  slots: StudioAgentRegistrySlotDTO[];
  pluginsBySlot: Record<string, StudioAgentRegistryPluginDTO[]>;
};

export type StudioAgentRegistryDTO = {
  version: number;
  modular: StudioAgentRegistryModularDTO;
  paramCatalog: Record<string, StudioRegistryParamGroupDTO[]>;
};
