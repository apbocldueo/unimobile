import { getStudioApiBase } from "@/services/studioRegistryClient";
import type { FlowDocumentV1 } from "@/modules/flow-graph/flowDocument";
import { tryParseFlowDocument } from "@/modules/flow-graph/flowDocument";

export type StudioFlowTemplateListItemDTO = {
  id: string;
  name: string;
  description: string;
};

/** 列出兵工厂预设模板（由后端 ``manifest.yaml`` 驱动）。无 API 时返回空数组。 */
export async function fetchStudioFlowTemplates(): Promise<StudioFlowTemplateListItemDTO[]> {
  const base = getStudioApiBase();
  if (!base) return [];
  const res = await fetch(`${base}/studio/flow-templates`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const hint404 =
      res.status === 404
        ? " — 请确认本机已运行 python -m zhixing.studio；若用 VITE_STUDIO_API_BASE 直连后端，应为 http://127.0.0.1:8765（不要带 /zhixing-studio，该前缀仅用于 Vite 代理）。npm run preview 时需配置代理或直连 8765。"
        : "";
    throw new Error(`flow_templates_http_${res.status}${hint404}`);
  }
  const json: unknown = await res.json();
  const raw = (json as { templates?: unknown }).templates;
  if (!Array.isArray(raw)) return [];
  const out: StudioFlowTemplateListItemDTO[] = [];
  for (const row of raw) {
    if (!row || typeof row !== "object") continue;
    const o = row as Record<string, unknown>;
    const id = typeof o.id === "string" ? o.id : "";
    const name = typeof o.name === "string" ? o.name : id;
    const description = typeof o.description === "string" ? o.description : "";
    if (!id) continue;
    out.push({ id, name, description });
  }
  return out;
}

/** 拉取单个模板文档 JSON 并校验为 ``FlowDocumentV1``。 */
export async function fetchStudioFlowTemplateDocument(id: string): Promise<FlowDocumentV1> {
  const base = getStudioApiBase();
  if (!base) throw new Error("flow_templates_no_api_base");
  const res = await fetch(`${base}/studio/flow-templates/${encodeURIComponent(id)}/document`, {
    headers: { Accept: "application/json" },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`flow_template_doc_http_${res.status}`);
  const parsed = tryParseFlowDocument(text);
  if (!parsed.ok) throw new Error(parsed.error);
  return parsed.doc;
}
