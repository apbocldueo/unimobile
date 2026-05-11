import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { BuilderStrategyId } from "@/domain/agent/builderStrategies";
import { STRATEGY_LABELS } from "@/domain/agent/builderStrategies";
import { useStudioModuleShellStore } from "@/stores/studioModuleShellStore";
import { useToastStore } from "@/stores/toastStore";
import { ChromePrimaryButton } from "@/app/shell/ChromePrimaryButton";
import { ChromeSecondaryButton } from "@/app/shell/ChromeSecondaryButton";

type RunRow = {
  id: string;
  flowName: string;
  strategyId: BuilderStrategyId;
  at: string;
  status: "成功" | "失败" | "运行中";
  result: string;
};

const MOCK: RunRow[] = [
  {
    id: "r1",
    flowName: STRATEGY_LABELS.modular,
    strategyId: "modular",
    at: "2026-05-06 09:12",
    status: "成功",
    result: "score 0.91",
  },
  {
    id: "r2",
    flowName: STRATEGY_LABELS.compact,
    strategyId: "compact",
    at: "2026-05-05 18:40",
    status: "失败",
    result: "timeout",
  },
  {
    id: "r3",
    flowName: STRATEGY_LABELS.modular,
    strategyId: "modular",
    at: "2026-05-04 11:05",
    status: "运行中",
    result: "—",
  },
];

/** 历史：侧栏联动 + 列表占位 + 跳转 Agent 构建（第四章 4.3） */
export function RunHistoryPage() {
  const navigate = useNavigate();
  const pushToast = useToastStore((s) => s.pushToast);
  const sidebarKey = useStudioModuleShellStore((s) => s.historySidebarKey);
  const [page, setPage] = useState(1);
  const [flowQuery, setFlowQuery] = useState("");
  const [status, setStatus] = useState<string>("全部");

  const filtered = useMemo(() => {
    return MOCK.filter((r) => {
      if (flowQuery.trim() && !r.flowName.toLowerCase().includes(flowQuery.trim().toLowerCase())) return false;
      if (status !== "全部" && r.status !== status) return false;
      return true;
    });
  }, [flowQuery, status]);

  const openInBuilder = (row: RunRow) => {
    navigate("/builder");
    pushToast({
      message: `已打开流程编辑。请在工具栏「加载模板」中选用「${row.flowName}」类参考拓扑（占位：后续由记录 ID 自动恢复画布）`,
      tone: "info",
      durationMs: 4800,
    });
  };

  const onExport = () => {
    pushToast({ message: "导出记录（占位）：后续接后端导出接口。", tone: "info", durationMs: 3800 });
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header
        className="shrink-0 border-b px-6 py-5"
        style={{ borderColor: "var(--zx-divider-ui)", backgroundColor: "var(--zx-canvas)" }}
      >
        <h1 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">运行历史</h1>
        <p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
          数据为前端占位；接入接口后与 Agent 构建流程配置同步展示。
        </p>
      </header>

      {sidebarKey === "filters" ? (
        <div
          className="shrink-0 border-b px-6 py-4"
          style={{ borderColor: "var(--zx-divider-ui)", backgroundColor: "rgba(0,0,0,0.18)" }}
        >
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex min-w-[10rem] flex-col gap-1 text-[11px] font-medium text-[color:var(--zx-text-muted)]">
              时间范围
              <input
                type="text"
                placeholder="例如 2026-05-01 ~ 2026-05-07"
                className="zx-control zx-body-sm px-3 py-2"
                readOnly
              />
            </label>
            <label className="flex min-w-[10rem] flex-col gap-1 text-[11px] font-medium text-[color:var(--zx-text-muted)]">
              流程名称
              <input
                className="zx-control zx-body-sm px-3 py-2"
                value={flowQuery}
                onChange={(e) => setFlowQuery(e.target.value)}
                placeholder="筛选名称"
              />
            </label>
            <label className="flex min-w-[8rem] flex-col gap-1 text-[11px] font-medium text-[color:var(--zx-text-muted)]">
              运行状态
              <select
                className="zx-control zx-body-sm cursor-pointer px-3 py-2"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                {["全部", "成功", "失败", "运行中"].map((s) => (
                  <option key={s} value={s} className="bg-[var(--zx-card)] text-[color:var(--zx-text-title)]">
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      ) : null}

      {sidebarKey === "export" ? (
        <div
          className="shrink-0 border-b px-6 py-4"
          style={{ borderColor: "var(--zx-divider-ui)", backgroundColor: "rgba(0,0,0,0.18)" }}
        >
          <p className="mb-3 max-w-xl text-[12px] text-[color:var(--zx-text-muted)]">
            导出当前筛选结果（占位）。接入后端后在此触发异步导出任务。
          </p>
          <ChromePrimaryButton onClick={onExport}>导出记录</ChromePrimaryButton>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[12px] text-[color:var(--zx-text-muted)]">
            共 <span className="tabular-nums text-[color:var(--zx-text-body)]">{filtered.length}</span> 条（分页占位）
          </p>
          <div className="flex items-center gap-2">
            <ChromeSecondaryButton disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              上一页
            </ChromeSecondaryButton>
            <span className="text-[12px] text-[color:var(--zx-text-muted)]">第 {page} 页</span>
            <ChromeSecondaryButton disabled={page >= 2} onClick={() => setPage((p) => p + 1)}>
              下一页
            </ChromeSecondaryButton>
          </div>
        </div>

        <div
          className="overflow-hidden rounded-lg border"
          style={{ borderColor: "var(--zx-border-light)", backgroundColor: "rgba(0,0,0,0.2)" }}
        >
          <table className="w-full border-collapse text-left text-[12px]">
            <thead>
              <tr className="border-b text-[11px] uppercase tracking-wide text-[color:var(--zx-text-muted)]" style={{ borderColor: "var(--zx-divider-ui)" }}>
                <th className="px-4 py-3 font-semibold">流程名称</th>
                <th className="px-4 py-3 font-semibold">运行时间</th>
                <th className="px-4 py-3 font-semibold">状态</th>
                <th className="px-4 py-3 font-semibold">结果</th>
                <th className="px-4 py-3 font-semibold">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} className="border-b last:border-0" style={{ borderColor: "var(--zx-divider-ui)" }}>
                  <td className="px-4 py-3 font-medium text-[color:var(--zx-text-title)]">{r.flowName}</td>
                  <td className="px-4 py-3 text-[color:var(--zx-text-body)]">{r.at}</td>
                  <td className="px-4 py-3 text-[color:var(--zx-text-body)]">{r.status}</td>
                  <td className="px-4 py-3 text-[color:var(--zx-text-muted)]">{r.result}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="rounded-md px-2 py-1 text-[11px] font-semibold text-[color:var(--zx-primary)] underline-offset-2 hover:underline"
                      onClick={() => openInBuilder(r)}
                    >
                      打开配置
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
