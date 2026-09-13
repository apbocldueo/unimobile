import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { StudioFlowDocument } from "@/entities/agent-graph";
import {
  saveAgentRevision,
  type AgentRevision,
} from "@/entities/agent-revision";
import { StudioApiError } from "@/shared/api";
import { useToastStore } from "@/stores/toastStore";
import { useAgentBuilderDocumentStore } from "./builder.store";

export type SaveAgentRevisionInput = {
  document: StudioFlowDocument;
  baseRevisionId: string | null;
};

/** Share one optimistic save boundary across Save and Save & Run commands. */
export function useSaveAgentRevisionCommand() {
  const queryClient = useQueryClient();
  const pushToast = useToastStore((state) => state.pushToast);
  const markSaved = useAgentBuilderDocumentStore((state) => state.markSaved);
  const setConflict = useAgentBuilderDocumentStore((state) => state.setConflict);
  return useMutation<
    { revision: AgentRevision },
    Error,
    SaveAgentRevisionInput
  >({
    mutationFn: async ({ document, baseRevisionId }) => {
      const result = await saveAgentRevision({
        agentId: document.agentId,
        baseRevisionId,
        document,
      });
      return { revision: result.revision };
    },
    onSuccess: async ({ revision }) => {
      markSaved(revision);
      await queryClient.invalidateQueries({
        queryKey: ["studio-agent", revision.agentId],
      });
      await queryClient.invalidateQueries({ queryKey: ["studio-agents"] });
      pushToast({
        message:
          revision.compileSnapshot.status === "valid"
            ? `Revision ${revision.ordinal} 已保存并校验通过`
            : `Revision ${revision.ordinal} 已作为 invalid draft 保存`,
        tone:
          revision.compileSnapshot.status === "valid" ? "success" : "warning",
        durationMs: 5200,
      });
    },
    onError: (error) => {
      if (error instanceof StudioApiError && error.status === 409) {
        setConflict(error.currentRevisionId);
        pushToast({
          message: "保存冲突：远端 current revision 已变化，不会自动覆盖",
          tone: "error",
          durationMs: 7000,
        });
        return;
      }
      pushToast({
        message: error.message || "保存失败",
        tone: "error",
      });
    },
  });
}
