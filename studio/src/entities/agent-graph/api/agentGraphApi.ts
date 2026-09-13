import { studioRequest } from "@/shared/api";
import type {
  LegacyStudioFlowDocument,
  StudioFlowDocument,
} from "../model/studioFlowDocument.schema";
import { parseLegacyStudioFlowDocument } from "../model/studioFlowDocument.schema";
import { isRecord } from "@/shared/lib";
import {
  parseStudioCompileResult,
  type StudioCompileResult,
} from "../model/compile.schema";

export type StudioFlowTemplateSummary = {
  id: string;
  name: string;
  description: string;
};

/** List backend-owned authoring templates without assuming their document schema. */
export async function listStudioFlowTemplates(): Promise<StudioFlowTemplateSummary[]> {
  const payload = await studioRequest("/studio/flow-templates");
  if (!isRecord(payload) || !Array.isArray(payload.templates)) {
    throw new Error("Template list response is invalid");
  }
  return payload.templates.map((item, index) => {
    if (!isRecord(item)) throw new Error(`templates[${index}] must be an object`);
    if (
      typeof item.id !== "string" ||
      typeof item.name !== "string" ||
      typeof item.description !== "string"
    ) {
      throw new Error(`templates[${index}] fields are invalid`);
    }
    return {
      id: item.id,
      name: item.name,
      description: item.description,
    };
  });
}

/** Read one template as unknown JSON so legacy schema 1 can use explicit migration. */
export async function getStudioFlowTemplateDocument(
  templateId: string,
): Promise<Record<string, unknown>> {
  const payload = await studioRequest(
    `/studio/flow-templates/${encodeURIComponent(templateId)}/document`,
  );
  if (!isRecord(payload)) throw new Error("Template document must be an object");
  return { ...payload };
}

/** Compile one Studio capability document without persisting it. */
export async function compileStudioDocument(
  document: StudioFlowDocument,
  catalogVersion?: string,
): Promise<StudioCompileResult> {
  const payload = await studioRequest("/studio/agent-graphs/compile", {
    method: "POST",
    body: JSON.stringify({
      schemaVersion: 1,
      document,
      ...(catalogVersion ? { catalogVersion } : {}),
    }),
  });
  return parseStudioCompileResult(payload);
}

/** Purely migrate a legacy schema 1 file while preserving the caller input. */
export async function migrateStudioDocument(
  document: Record<string, unknown>,
  agentId?: string,
): Promise<{
  isSuccess: boolean;
  document: LegacyStudioFlowDocument | null;
  diagnostics: unknown[];
}> {
  const payload = await studioRequest("/studio/flow-documents/migrate", {
    method: "POST",
    body: JSON.stringify({
      schemaVersion: 1,
      document,
      ...(agentId ? { agentId } : {}),
    }),
  });
  if (!isRecord(payload) || payload.schemaVersion !== 1 || typeof payload.isSuccess !== "boolean") {
    throw new Error("Migration response is invalid");
  }
  return {
    isSuccess: payload.isSuccess,
    document: payload.document === null ? null : parseLegacyStudioFlowDocument(payload.document),
    diagnostics: Array.isArray(payload.diagnostics) ? [...payload.diagnostics] : [],
  };
}
