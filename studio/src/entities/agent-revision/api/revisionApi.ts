import type { StudioFlowDocument } from "@/entities/agent-graph";
import { parseStudioAgent, type StudioAgent } from "@/entities/agent";
import { studioRequest } from "@/shared/api";
import { isRecord } from "@/shared/lib";
import { parseAgentRevision, type AgentRevision } from "../model/revision.schema";

/** Read one immutable revision by stable resource identity. */
export async function getAgentRevision(
  agentId: string,
  revisionId: string,
): Promise<AgentRevision> {
  const value = await studioRequest(
    `/studio/agents/${encodeURIComponent(agentId)}/revisions/${encodeURIComponent(revisionId)}`,
  );
  if (!isRecord(value) || value.schemaVersion !== 1) throw new Error("Revision response is invalid");
  return parseAgentRevision(value.revision);
}

/** Append one revision using optimistic current-revision validation. */
export async function saveAgentRevision(input: {
  agentId: string;
  baseRevisionId: string | null;
  document: StudioFlowDocument;
}): Promise<{ agent: StudioAgent; revision: AgentRevision }> {
  const value = await studioRequest(
    `/studio/agents/${encodeURIComponent(input.agentId)}/revisions`,
    {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: 1,
        baseRevisionId: input.baseRevisionId,
        document: input.document,
      }),
    },
  );
  if (!isRecord(value) || value.schemaVersion !== 1) throw new Error("Save revision response is invalid");
  return {
    agent: parseStudioAgent(value.agent),
    revision: parseAgentRevision(value.revision),
  };
}
