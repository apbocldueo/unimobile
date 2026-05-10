import { useModuleNavSwitch } from "./ModuleNavSwitchContext";

/**
 * 模块切换失败时，在画布主区域顶部展示简短提示与重试（第三章 3.1）。
 */
export function CanvasModuleNavBanner() {
  const { errorPath, retry } = useModuleNavSwitch();

  if (!errorPath) return null;

  return (
    <div
      className="pointer-events-auto absolute inset-x-0 top-0 z-[20] flex items-center justify-center gap-3 border-b px-4 py-2.5 text-[13px]"
      style={{
        backgroundColor: "rgba(26, 26, 26, 0.96)",
        borderColor: "rgba(255, 107, 107, 0.35)",
        color: "#ff6b6b",
      }}
      role="alert"
    >
      <span className="font-medium">模块加载失败，请重试</span>
      <button
        type="button"
        className="rounded-lg border border-[rgba(255,107,107,0.55)] bg-transparent px-3 py-1 text-[12px] font-semibold text-[#ff6b6b] outline-none transition-[background-color,color] hover:bg-[rgba(255,107,107,0.12)] focus-visible:ring-2 focus-visible:ring-[#ff6b6b] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-canvas)]"
        onClick={() => void retry()}
      >
        重试
      </button>
    </div>
  );
}
