import { isRecord, requireNumber, requireString } from "@/shared/lib";

export type StudioAgent = {
  agentId: string;
  name: string;
  currentRevisionId: string | null;
  createdAt: number;
  updatedAt: number;
};

/** Parse one mutable Agent metadata record. */
export function parseStudioAgent(value: unknown, path = "agent"): StudioAgent {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  return {
    agentId: requireString(value.agentId, `${path}.agentId`),
    name: requireString(value.name, `${path}.name`),
    currentRevisionId:
      value.currentRevisionId === null || value.currentRevisionId === undefined
        ? null
        : requireString(value.currentRevisionId, `${path}.currentRevisionId`),
    createdAt: requireNumber(value.createdAt, `${path}.createdAt`),
    updatedAt: requireNumber(value.updatedAt, `${path}.updatedAt`),
  };
}
