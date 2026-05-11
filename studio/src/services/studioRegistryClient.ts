import { BUILDER_STRATEGY_IDS, type BuilderStrategyId } from "@/domain/agent/builderStrategies";
import type {
  StudioAgentRegistryDTO,
  StudioAgentRegistryModularDTO,
  StudioAgentRegistryPluginDTO,
  StudioAgentRegistrySlotDTO,
  StudioRegistryParamFieldDTO,
  StudioRegistryParamGroupDTO,
} from "@/domain/agent/agentRegistryTypes";
import type { FlowComponentDef } from "@/domain/agent/flowComponents";
import type { StudioModuleConfigDTO, StudioNavModuleDTO } from "@/domain/studio/registryTypes";

/**
 * 直连 ``python -m zhixing.studio`` 时接口在根路径下（``/studio/...``）。
 * 若把 Vite 开发用的代理前缀 ``/zhixing-studio`` 一并写进绝对地址，会得到 ``…/zhixing-studio/studio/…``，后端返回 404。
 */
function normalizeStudioApiBase(raw: string): string {
  const s0 = raw.trim().replace(/\/+$/, "");
  if (!s0) return s0;
  /** 相对路径：保留，供 Vite dev/preview 同源代理使用 */
  if (s0.startsWith("/")) return s0;
  try {
    const u = new URL(s0);
    const path = (u.pathname || "/").replace(/\/+$/, "") || "/";
    if (path === "/zhixing-studio" || path.endsWith("/zhixing-studio")) {
      const nextPath =
        path === "/zhixing-studio" ? "/" : `${path.slice(0, -"/zhixing-studio".length) || "/"}`.replace(/\/+$/, "") || "/";
      u.pathname = nextPath.startsWith("/") ? nextPath : `/${nextPath}`;
      const joined = `${u.origin}${u.pathname === "/" ? "" : u.pathname}`;
      return joined.replace(/\/+$/, "");
    }
  } catch {
    /* 非 URL 则原样返回（极少见） */
  }
  return s0;
}

function apiBase(): string | null {
  const raw = typeof import.meta !== "undefined" ? (import.meta.env?.VITE_STUDIO_API_BASE as string | undefined) : undefined;
  if (raw && typeof raw === "string" && raw.trim()) return normalizeStudioApiBase(raw);
  /** 开发构建：走 Vite 同源代理到本机 8765，无需手写 .env 即可连 ``python -m zhixing.studio`` */
  if (typeof import.meta !== "undefined" && import.meta.env?.DEV) return "/zhixing-studio";
  return null;
}

/** 供其他模块判断是否应请求 Studio 元数据接口 */
export function getStudioApiBase(): string | null {
  return apiBase();
}

/** 无后端或未配置 VITE_STUDIO_API_BASE 时的默认导航（与现网一致） */
export const STUDIO_DEFAULT_NAV_MODULES: StudioNavModuleDTO[] = [
  { id: "builder", name: "Agent 构建", iconKey: "bot", order: 10, path: "/builder", allowed: true },
  { id: "benchmark", name: "试车场", iconKey: "lineChart", order: 20, path: "/benchmark", allowed: true },
  { id: "history", name: "历史", iconKey: "history", order: 30, path: "/history", allowed: true },
  { id: "settings", name: "设置", iconKey: "settings", order: 40, path: "/settings", allowed: true },
];

const KNOWN_PATHS = new Set(["/builder", "/benchmark", "/history", "/settings"]);

function coerceNavModule(x: unknown): StudioNavModuleDTO | null {
  if (!x || typeof x !== "object") return null;
  const o = x as Record<string, unknown>;
  const id = typeof o.id === "string" ? o.id : typeof o.moduleId === "string" ? o.moduleId : "";
  const name = typeof o.name === "string" ? o.name : typeof o.moduleName === "string" ? (o.moduleName as string) : "";
  const iconKey = typeof o.iconKey === "string" ? o.iconKey : typeof o.icon === "string" ? (o.icon as string) : "bot";
  const order = typeof o.order === "number" ? o.order : Number(o.order) || 0;
  const rawPath = typeof o.path === "string" ? o.path : "";
  const path = rawPath.startsWith("/") ? rawPath : rawPath ? `/${rawPath}` : "";
  const disabled = Boolean(o.disabled);
  const allowed = o.allowed === undefined ? true : Boolean(o.allowed);
  if (!id || !name || !path || !KNOWN_PATHS.has(path)) return null;
  return { id, name, iconKey, order, path, disabled, allowed };
}

/** 6.1：拉取顶部模块列表；失败则回退默认列表 */
export async function fetchNavModules(): Promise<{ modules: StudioNavModuleDTO[]; source: "remote" | "fallback" }> {
  const base = apiBase();
  if (!base) return { modules: STUDIO_DEFAULT_NAV_MODULES, source: "fallback" };
  try {
    const res = await fetch(`${base}/studio/nav-modules`, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`nav_modules_http_${res.status}`);
    const json: unknown = await res.json();
    const rawList = Array.isArray((json as { modules?: unknown }).modules)
      ? (json as { modules: unknown[] }).modules
      : Array.isArray(json)
        ? (json as unknown[])
        : [];
    const parsed = rawList.map(coerceNavModule).filter(Boolean) as StudioNavModuleDTO[];
    if (parsed.length === 0) return { modules: STUDIO_DEFAULT_NAV_MODULES, source: "fallback" };
    return { modules: parsed.sort((a, b) => a.order - b.order), source: "remote" };
  } catch {
    return { modules: STUDIO_DEFAULT_NAV_MODULES, source: "fallback" };
  }
}

function mockModuleConfig(moduleId: string): StudioModuleConfigDTO {
  return {
    moduleId,
    permission: "allow",
    sidebarItems: [],
  };
}

/** 6.2：模块配置；无后端时返回占位，供缓存与后续侧栏接入 */
export async function fetchModuleConfig(moduleId: string): Promise<StudioModuleConfigDTO> {
  const base = apiBase();
  if (!base) return mockModuleConfig(moduleId);
  try {
    const res = await fetch(`${base}/studio/module-config?moduleId=${encodeURIComponent(moduleId)}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`module_config_http_${res.status}`);
    const json = (await res.json()) as StudioModuleConfigDTO;
    if (!json || typeof json !== "object" || !json.moduleId) return mockModuleConfig(moduleId);
    return {
      moduleId: json.moduleId,
      permission: json.permission === "deny" ? "deny" : "allow",
      sidebarItems: Array.isArray(json.sidebarItems) ? json.sidebarItems : [],
    };
  } catch {
    return mockModuleConfig(moduleId);
  }
}

function isStrategyId(x: string): x is BuilderStrategyId {
  return (BUILDER_STRATEGY_IDS as readonly string[]).includes(x);
}

/** 6.3：流程卡片目录；返回 null 表示沿用前端内置 catalog */
export async function fetchBuilderFlowCatalog(): Promise<FlowComponentDef[] | null> {
  const base = apiBase();
  if (!base) return null;
  try {
    const res = await fetch(`${base}/studio/builder/flows`, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`flows_http_${res.status}`);
    const json: unknown = await res.json();
    const flows = Array.isArray((json as { flows?: unknown }).flows)
      ? (json as { flows: unknown[] }).flows
      : Array.isArray(json)
        ? (json as unknown[])
        : [];
    const out: FlowComponentDef[] = [];
    for (const row of flows) {
      if (!row || typeof row !== "object") continue;
      const o = row as Record<string, unknown>;
      const sid = typeof o.strategyId === "string" ? o.strategyId : "";
      if (!isStrategyId(sid)) continue;
      const title = typeof o.title === "string" ? o.title : sid;
      const description = typeof o.description === "string" ? o.description : "";
      out.push({ strategyId: sid, title, description, enabled: o.enabled !== false });
    }
    return out.length ? out : null;
  } catch {
    return null;
  }
}

function parseHint(v: unknown): string | undefined {
  if (v === null || v === undefined) return undefined;
  if (typeof v !== "string") return undefined;
  return v;
}

function parseParamField(row: unknown): StudioRegistryParamFieldDTO | null {
  if (!row || typeof row !== "object") return null;
  const o = row as Record<string, unknown>;
  const id = typeof o.id === "string" ? o.id : "";
  const label = typeof o.label === "string" ? o.label : id;
  const hint = parseHint(o.hint);
  const kind = o.kind === "select" || o.kind === "text" || o.kind === "number" ? o.kind : null;
  if (!id || !kind) return null;
  if (kind === "select") {
    const optsRaw = Array.isArray(o.options) ? o.options : [];
    const options = optsRaw
      .map((x) => {
        if (!x || typeof x !== "object") return null;
        const r = x as Record<string, unknown>;
        const value = typeof r.value === "string" ? r.value : "";
        const ol = typeof r.label === "string" ? r.label : value;
        return value ? { value, label: ol } : null;
      })
      .filter(Boolean) as { value: string; label: string }[];
    const defaultValue = typeof o.defaultValue === "string" ? o.defaultValue : options[0]?.value ?? "";
    return { id, label, hint, kind: "select", options, defaultValue };
  }
  if (kind === "number") {
    const dv = typeof o.defaultValue === "number" ? o.defaultValue : Number(o.defaultValue) || 0;
    const min = typeof o.min === "number" ? o.min : o.min !== undefined ? Number(o.min) : undefined;
    const max = typeof o.max === "number" ? o.max : o.max !== undefined ? Number(o.max) : undefined;
    const out: StudioRegistryParamFieldDTO = {
      id,
      label,
      hint,
      kind: "number",
      defaultValue: dv,
    };
    if (min !== undefined && !Number.isNaN(min)) out.min = min;
    if (max !== undefined && !Number.isNaN(max)) out.max = max;
    return out;
  }
  const defaultValue = typeof o.defaultValue === "string" ? o.defaultValue : "";
  const placeholder = typeof o.placeholder === "string" ? o.placeholder : undefined;
  return { id, label, hint, kind: "text", defaultValue, placeholder };
}

function parseParamGroup(row: unknown): StudioRegistryParamGroupDTO | null {
  if (!row || typeof row !== "object") return null;
  const o = row as Record<string, unknown>;
  const id = typeof o.id === "string" ? o.id : "";
  const title = typeof o.title === "string" ? o.title : id;
  const tier = o.tier === "advanced" || o.tier === "core" ? o.tier : undefined;
  const fieldsRaw = Array.isArray(o.fields) ? o.fields : [];
  const fields = fieldsRaw.map(parseParamField).filter(Boolean) as StudioRegistryParamFieldDTO[];
  if (!id || !title) return null;
  return { id, title, tier, fields };
}

function parsePlugin(row: unknown): StudioAgentRegistryPluginDTO | null {
  if (!row || typeof row !== "object") return null;
  const o = row as Record<string, unknown>;
  const id = typeof o.id === "string" ? o.id : "";
  const namespace = typeof o.namespace === "string" ? o.namespace : "";
  const className = typeof o.className === "string" ? o.className : "";
  const title = typeof o.title === "string" ? o.title : className || id;
  const description = typeof o.description === "string" ? o.description : "";
  const pgRaw = Array.isArray(o.paramGroups) ? o.paramGroups : [];
  const paramGroups = pgRaw.map(parseParamGroup).filter(Boolean) as StudioRegistryParamGroupDTO[];
  if (!id || !namespace) return null;
  return { id, namespace, className, title, description, paramGroups };
}

function parseSlot(row: unknown): StudioAgentRegistrySlotDTO | null {
  if (!row || typeof row !== "object") return null;
  const o = row as Record<string, unknown>;
  const slotId = typeof o.slotId === "string" ? o.slotId : "";
  const title = typeof o.title === "string" ? o.title : "";
  const roleLabel = typeof o.roleLabel === "string" ? o.roleLabel : "";
  /** 与 ``zhixing/studio/agent_registry.py`` 下发的 ``baseDescription``（源自 interfaces.Base*._description）对齐 */
  const baseDescriptionRaw = o.baseDescription ?? o.base_description;
  const baseDescription =
    typeof baseDescriptionRaw === "string" && baseDescriptionRaw.trim() ? baseDescriptionRaw.trim() : undefined;
  if (!slotId || !title) return null;
  return { slotId, title, roleLabel: roleLabel || title, ...(baseDescription ? { baseDescription } : {}) };
}

function parseModular(row: unknown): StudioAgentRegistryModularDTO | null {
  if (!row || typeof row !== "object") return null;
  const o = row as Record<string, unknown>;
  const strategyId = o.strategyId === "modular" ? "modular" : null;
  const backendPluginName = typeof o.backendPluginName === "string" ? o.backendPluginName : "";
  const title = typeof o.title === "string" ? o.title : "";
  const description = typeof o.description === "string" ? o.description : "";
  const slotsRaw = Array.isArray(o.slots) ? o.slots : [];
  const slots = slotsRaw.map(parseSlot).filter(Boolean) as StudioAgentRegistrySlotDTO[];
  const pbs = o.pluginsBySlot;
  const pluginsBySlot: Record<string, StudioAgentRegistryPluginDTO[]> = {};
  if (pbs && typeof pbs === "object") {
    for (const [k, v] of Object.entries(pbs as Record<string, unknown>)) {
      if (!Array.isArray(v)) continue;
      const list = v.map(parsePlugin).filter(Boolean) as StudioAgentRegistryPluginDTO[];
      pluginsBySlot[k] = list;
    }
  }
  if (!strategyId || !backendPluginName || slots.length === 0) return null;
  return {
    strategyId,
    backendPluginName,
    title,
    description,
    slots,
    pluginsBySlot,
  };
}

/** 拉取 ZhiXing 侧 Modular 槽位、分槽插件列表与参数 schema；无后端或未配置 base 时返回 null；网络/HTTP 错误则抛出供上层展示原因。 */
export async function fetchAgentBuilderRegistry(): Promise<StudioAgentRegistryDTO | null> {
  const base = apiBase();
  if (!base) return null;
  const res = await fetch(`${base}/studio/builder/agent-registry`, { headers: { Accept: "application/json" } });
  const rawText = await res.text();
  if (!res.ok) {
    let detail = "";
    try {
      const ej = JSON.parse(rawText) as { message?: string; error?: string };
      if (typeof ej.message === "string" && ej.message.trim()) detail = ej.message.trim().slice(0, 900);
      else if (typeof ej.error === "string") detail = ej.error;
    } catch {
      /* ignore */
    }
    throw new Error(detail ? `元数据接口 HTTP ${res.status} — ${detail}` : `元数据接口 HTTP ${res.status}`);
  }
  let json: unknown;
  try {
    json = JSON.parse(rawText) as unknown;
  } catch {
    return null;
  }
  if (!json || typeof json !== "object") return null;
  const root = json as Record<string, unknown>;
  const version = typeof root.version === "number" ? root.version : Number(root.version) || 0;
  const modular = parseModular(root.modular);
  if (!modular) return null;
  const pcRaw = root.paramCatalog;
  const paramCatalog: Record<string, StudioRegistryParamGroupDTO[]> = {};
  if (pcRaw && typeof pcRaw === "object") {
    for (const [pid, groups] of Object.entries(pcRaw as Record<string, unknown>)) {
      if (!Array.isArray(groups)) continue;
      const parsed = groups.map(parseParamGroup).filter(Boolean) as StudioRegistryParamGroupDTO[];
      paramCatalog[pid] = parsed;
    }
  }
  return { version, modular, paramCatalog };
}
