import { useMemo } from "react";
import { useAgentBuilderStore } from "@/stores/agentBuilderStore";
import { useStudioAgentRegistryStore } from "@/stores/studioAgentRegistryStore";
import { getSlotMeta } from "@/domain/agent/slotMeta";
import { SlotGlyph } from "@/components/icons/SlotGlyph";
import type { StudioAgentRegistryPluginDTO } from "@/domain/agent/agentRegistryTypes";

const EMPTY_PLUGINS: StudioAgentRegistryPluginDTO[] = [];

export function PluginShowcasePanel() {
  const selectedSlotId = useAgentBuilderStore((s) => s.selectedSlotId);
  const pickPlugin = useAgentBuilderStore((s) => s.pickPluginPlaceholder);
  const meta = selectedSlotId ? getSlotMeta(selectedSlotId) : null;

  const pluginsFromStore = useStudioAgentRegistryStore((s) => {
    if (!selectedSlotId || !s.data?.modular?.pluginsBySlot) return undefined;
    return s.data.modular.pluginsBySlot[selectedSlotId];
  });

  const plugins = useMemo(() => pluginsFromStore ?? EMPTY_PLUGINS, [pluginsFromStore]);

  return (
    <div className="flex flex-col gap-4 text-sm">
      <p className="zx-body-sm flex flex-wrap items-center gap-x-2 gap-y-2 leading-relaxed">
        <span>正在为</span>
        {selectedSlotId ? <SlotGlyph slotId={selectedSlotId} size={18} /> : null}
        <span className="zx-type-title text-[color:var(--zx-text-title)]">
          {meta ? meta.titleEn : selectedSlotId ?? "—"}
        </span>
        <span>选择算法实现</span>
      </p>
      {plugins.length === 0 ? (
        <p className="zx-body-sm leading-relaxed" style={{ color: "var(--zx-text-muted)" }}>
          未连接 ZhiXing 元数据服务或未拉取到该槽位的插件列表。请在仓库根目录运行{" "}
          <code className="rounded bg-black/30 px-1 py-0.5 text-[11px]">python -m zhixing.studio</code>{" "}
          并在 Studio 配置 <code className="rounded bg-black/30 px-1 py-0.5 text-[11px]">VITE_STUDIO_API_BASE</code>{" "}
          指向该服务；亦可暂时使用画布卡片上的快速占位入口。
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {plugins.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className="w-full rounded-lg border-2 p-4 text-left transition-[background-color,border-color]"
                style={{
                  borderColor: "var(--zx-control-border)",
                  backgroundColor: "var(--zx-control-bg)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--zx-primary)";
                  e.currentTarget.style.backgroundColor = "var(--zx-control-bg-hover)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--zx-control-border)";
                  e.currentTarget.style.backgroundColor = "var(--zx-control-bg)";
                }}
                onClick={() => pickPlugin(p.id, p.title || p.className, selectedSlotId ?? undefined)}
              >
                <div className="zx-type-title text-[color:var(--zx-primary)]">{p.title || p.className}</div>
                <div className="zx-body-sm mt-1 font-mono text-[11px] opacity-70">{p.id}</div>
                {p.description ? (
                  <div className="zx-body-sm mt-2 leading-snug" style={{ color: "var(--zx-text-body)" }}>
                    {p.description}
                  </div>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
