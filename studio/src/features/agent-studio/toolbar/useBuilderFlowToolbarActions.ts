import { useCallback, useState } from "react";
import { countIncompleteForStrategy } from "@/domain/agent/flowCompletion";
import { useAgentBuilderStore } from "@/stores/agentBuilderStore";
import { useToastStore } from "@/stores/toastStore";

/** 占位延迟；接入真实 API 后改为 await 原有封装（地址/参数/返回值不变）。 */
function pendingDelay(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/**
 * 兵工厂底部栏：保存 / 运行 / 重置 的交互与请求态。
 * 与 UI 解耦，便于新增「导出配置」等按钮时复用同一调用规范（第五章 5.2）。
 */
export function useBuilderFlowToolbarActions() {
  const selectedStrategyId = useAgentBuilderStore((s) => s.selectedStrategyId);
  const assignments = useAgentBuilderStore((s) => s.assignments);
  const slotParamsTouched = useAgentBuilderStore((s) => s.slotParamsTouched);
  const resetBuilderDraft = useAgentBuilderStore((s) => s.resetBuilderDraft);
  const pushToast = useToastStore((s) => s.pushToast);

  const [savePending, setSavePending] = useState(false);
  const [resetPending, setResetPending] = useState(false);
  const [runPending, setRunPending] = useState(false);

  const incomplete = countIncompleteForStrategy(assignments, slotParamsTouched, selectedStrategyId);
  const flowReady = incomplete === 0;

  const onReset = useCallback(async () => {
    if (resetPending) return;
    setResetPending(true);
    try {
      await pendingDelay(380);
      resetBuilderDraft();
      pushToast({ message: "重置成功", tone: "info", durationMs: 3000 });
    } finally {
      setResetPending(false);
    }
  }, [resetBuilderDraft, resetPending, pushToast]);

  const onSave = useCallback(async () => {
    if (savePending) return;
    setSavePending(true);
    try {
      await pendingDelay(420);
      pushToast({ message: "配置已保存", tone: "info", durationMs: 3000 });
    } finally {
      setSavePending(false);
    }
  }, [savePending, pushToast]);

  const onRun = useCallback(async () => {
    if (runPending) return;
    if (!flowReady) {
      pushToast({
        message: "流程未配置完成，请先完成所有组件的算法选择与参数配置",
        tone: "warning",
        durationMs: 5000,
      });
      return;
    }
    setRunPending(true);
    pushToast({ message: "运行中", tone: "info", durationMs: 3000 });
    try {
      await pendingDelay(900);
      pushToast({ message: "运行完成（占位：后续将展示执行结果）", tone: "success", durationMs: 3000 });
    } finally {
      setRunPending(false);
    }
  }, [flowReady, runPending, pushToast]);

  return {
    flowReady,
    incomplete,
    savePending,
    resetPending,
    runPending,
    onSave,
    onRun,
    onReset,
  };
}
