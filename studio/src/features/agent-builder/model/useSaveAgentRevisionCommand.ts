import { uiMessage, uiText } from "@/shared/i18n";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import type { StudioFlowDocument } from "@/entities/agent-graph";
import {
  saveAgentRevision,
  type AgentRevision,
} from "@/entities/agent-revision";
import { StudioApiError } from "@/shared/api";
import { useToastStore } from "@/stores/toastStore";
import { useAgentBuilderDocumentStore } from "./builder.store";
import type { EditSnapshot } from "./editSession";

export type SaveAgentRevisionInput = {
  document: StudioFlowDocument;
  baseRevisionId: string | null;
  snapshot: EditSnapshot;
};

/** Share one optimistic save boundary across Save and Save & Run commands. */
export function useSaveAgentRevisionCommand() {
  const queryClient = useQueryClient();
  const pushToast = useToastStore((state) => state.pushToast);
  const acknowledgeSave = useAgentBuilderDocumentStore((state) => state.acknowledgeSave);
  const setConflict = useAgentBuilderDocumentStore((state) => state.setConflict);
  const started = useRef(new WeakSet<SaveAgentRevisionInput>());
  return useMutation<
    { revision: AgentRevision; snapshot: EditSnapshot },
    Error,
    SaveAgentRevisionInput
  >({
    mutationFn: async (input) => {
      const state = useAgentBuilderDocumentStore.getState();
      if (!state.matchesSnapshot(input.snapshot) || state.baseRevisionId !== input.snapshot.baseRevisionId) throw new Error(uiText("编辑内容已变化，请重新保存。"));
      if (state.savePending) throw new Error(uiText("已有保存正在进行，请等待完成。"));
      if (state.conflictRevisionId) throw new Error(uiText("请先处理 revision 冲突，或另存为新的 Agent。"));
      const snapshot = input.snapshot;
      started.current.add(input);
      useAgentBuilderDocumentStore.setState({ savePending: true });
      const result = await saveAgentRevision({
        agentId: snapshot.document.agentId,
        baseRevisionId: snapshot.baseRevisionId,
        document: snapshot.document,
      });
      return { revision: result.revision, snapshot };
    },
    onSuccess: async ({ revision, snapshot }) => {
      acknowledgeSave(snapshot, revision);
      await queryClient.invalidateQueries({
        queryKey: ["studio-agent", revision.agentId],
      });
      await queryClient.invalidateQueries({ queryKey: ["studio-agents"] });
      const current = useAgentBuilderDocumentStore.getState();
      if (current.sessionId !== snapshot.sessionId) return;
      pushToast({
        message:
          !current.matchesSnapshot(snapshot) ? uiMessage`Revision ${revision.ordinal} 已保存；仍有更新的编辑未保存` : revision.compileSnapshot.status === "valid"
            ? uiMessage`Revision ${revision.ordinal} 已保存并校验通过`
            : uiMessage`Revision ${revision.ordinal} 已作为 invalid draft 保存`,
        tone:
          revision.compileSnapshot.status === "valid" ? "success" : "warning",
        durationMs: 5200,
      });
    },
    onError: (error, input) => {
      if (useAgentBuilderDocumentStore.getState().sessionId !== input.snapshot.sessionId) return;
      if (error instanceof StudioApiError && error.status === 409) {
        setConflict(error.currentRevisionId);
        pushToast({
          message: uiText("保存冲突：远端 current revision 已变化，不会自动覆盖"),
          tone: "error",
          durationMs: 7000,
        });
        return;
      }
      pushToast({
        message: error.message || uiText("保存失败"),
        tone: "error",
      });
    },
    onSettled: (_data, _error, input) => {
      if (started.current.has(input) && useAgentBuilderDocumentStore.getState().sessionId === input.snapshot.sessionId) {
        useAgentBuilderDocumentStore.setState({ savePending: false });
      }
      started.current.delete(input);
    },
  });
}
