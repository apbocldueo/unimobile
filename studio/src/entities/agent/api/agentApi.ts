import { studioRequest } from "@/shared/api";
import { isRecord } from "@/shared/lib";
import type { StudioFlowDocument } from "@/entities/agent-graph";
import { parseAgentRevision, type AgentRevision } from "@/entities/agent-revision";
import { parseStudioAgent, type StudioAgent } from "../model/agent.schema";

export type AgentDetail = {
  agent: StudioAgent;
  currentRevision: AgentRevision | null;
};

export type AgentPage = {
  items: StudioAgent[];
  nextCursor: string | null;
};

/** List persisted Studio Agents with a bounded server cursor. */
export async function listStudioAgents(limit = 50, cursor?: string): Promise<AgentPage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  const value = await studioRequest(`/studio/agents?${query.toString()}`);
  if (!isRecord(value) || value.schemaVersion !== 1 || !Array.isArray(value.items)) {
    throw new Error("Agent list response is invalid");
  }
  return {
    items: value.items.map((item, index) => parseStudioAgent(item, `items[${index}]`)),
    nextCursor: typeof value.nextCursor === "string" ? value.nextCursor : null,
  };
}

/** Load one Agent and its immutable current revision. */
export async function getStudioAgent(agentId: string): Promise<AgentDetail> {
  const value = await studioRequest(`/studio/agents/${encodeURIComponent(agentId)}`);
  if (!isRecord(value) || value.schemaVersion !== 1) throw new Error("Agent response is invalid");
  return {
    agent: parseStudioAgent(value.agent),
    currentRevision:
      value.currentRevision === null
        ? null
        : parseAgentRevision(value.currentRevision, "currentRevision"),
  };
}

/** Create one Agent with an empty or supplied schema 2 initial revision. */
export async function createStudioAgent(
  name: string,
  initialDocument?: StudioFlowDocument,
): Promise<AgentDetail> {
  const value = await studioRequest("/studio/agents", {
    method: "POST",
    body: JSON.stringify({
      schemaVersion: 1,
      name,
      ...(initialDocument ? { initialDocument } : {}),
    }),
  });
  if (!isRecord(value) || value.schemaVersion !== 1) throw new Error("Create Agent response is invalid");
  return {
    agent: parseStudioAgent(value.agent),
    currentRevision: parseAgentRevision(value.currentRevision, "currentRevision"),
  };
}

/** Rename mutable Agent metadata without creating a revision. */
export async function renameStudioAgent(agentId: string, name: string): Promise<StudioAgent> {
  const value = await studioRequest(`/studio/agents/${encodeURIComponent(agentId)}`, {
    method: "PATCH",
    body: JSON.stringify({ schemaVersion: 1, name }),
  });
  if (!isRecord(value) || value.schemaVersion !== 1) throw new Error("Rename Agent response is invalid");
  return parseStudioAgent(value.agent);
}
