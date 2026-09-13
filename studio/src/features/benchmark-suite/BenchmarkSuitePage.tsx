import { useMemo } from "react";
import { useStudioModuleShellStore } from "@/stores/studioModuleShellStore";

const PLACEHOLDER =
  "试车场画布占位：后续将在此加载任务列表、基准测试仪表盘等内容。接口返回后可直接替换本区域，无需改动顶栏与侧栏联动框架。";

/** 试车场：侧栏联动 + 画布占位（第四章 4.2） */
export function BenchmarkSuitePage() {
  const key = useStudioModuleShellStore((s) => s.benchmarkSidebarKey);

  const title = useMemo(() => {
    if (key === "tasks") return "任务列表";
    if (key === "benchmark") return "基准配置";
    return "参数设置";
  }, [key]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header
        className="shrink-0 border-b px-6 py-5"
        style={{ borderColor: "var(--zx-divider-ui)", backgroundColor: "var(--zx-canvas)" }}
      >
        <h1 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">试车场 · {title}</h1>
        <p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
          左侧入口由后端接口动态返回时可映射到同一 store；当前为静态占位。
        </p>
      </header>
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 px-6 py-10 text-center">
        <div
          className="max-w-md rounded-lg border px-5 py-6 text-[13px] leading-relaxed text-[color:var(--zx-text-body)]"
          style={{
            borderColor: "var(--zx-border-light)",
            backgroundColor: "rgba(0,0,0,0.2)",
          }}
        >
          <p className="font-medium text-[color:var(--zx-text-title)]">请选择左侧任务进入测试</p>
          <p className="mt-3 text-[color:var(--zx-text-muted)]">{PLACEHOLDER}</p>
        </div>
      </div>
    </div>
  );
}
