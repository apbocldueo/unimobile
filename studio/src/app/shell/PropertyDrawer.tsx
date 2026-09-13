import { IconCheck, IconPanelLeft, IconSettings } from "@/components/icons/StudioIcons";
import { ChromePrimaryButton } from "./ChromePrimaryButton";
import { ChromeSecondaryButton } from "./ChromeSecondaryButton";
import { useLocation } from "react-router-dom";
import type { AgentDrawerMode } from "@/features/agent-studio/panels/drawerTypes";
import { BuilderSlotParamsPanel } from "@/features/agent-studio/panels/BuilderSlotParamsPanel";
import { PluginShowcasePanel } from "@/features/agent-studio/panels/PluginShowcasePanel";
import { useAgentBuilderStore } from "@/stores/agentBuilderStore";
import { getSlotMeta } from "@/domain/agent/slotMeta";
import { SlotGlyph } from "@/components/icons/SlotGlyph";
import { buildParamValueErrors, getDefaultSlotParamValues, getPluginParamGroups } from "@/domain/agent/pluginParamUi";
import { STUDIO_BUILDER_FLOATING_SURFACE_CLASS } from "./studioBuilderChrome";

const LABEL_COLOR = "rgba(185,193,208,0.85)";

function DrawerEmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-full min-h-[240px] flex-1 flex-col items-center justify-center gap-4 px-6 py-6 text-center">
      <IconPanelLeft size={32} strokeWidth={1.75} style={{ color: "var(--zx-text-muted)" }} aria-hidden />
      <p className="zx-body-sm max-w-[240px]">{message}</p>
    </div>
  );
}

const drawerShellDefault =
  "flex w-[22rem] shrink-0 flex-col overflow-hidden rounded-xl border bg-[var(--zx-panel)] shadow-[var(--zx-shadow-soft)]";

const drawerShellBuilder = "flex w-[300px] shrink-0 flex-col overflow-hidden rounded-lg";

function formatAlgorithmLine(pluginId: string, pluginTitle: string) {
  if (pluginId === "som") return "当前算法：SOM";
  if (pluginId === "screenshot") return "当前算法：Screenshot";
  return `当前算法：${pluginTitle}`;
}

function DrawerHeaderBlock({
  drawerMode,
  headerSlotId,
  meta,
  assignments,
}: {
  drawerMode: AgentDrawerMode;
  headerSlotId: string | null;
  meta: ReturnType<typeof getSlotMeta> | null;
  assignments: Record<string, { pluginId: string; pluginTitle: string }>;
}) {
  if (drawerMode === "plugin_showcase" && meta && headerSlotId) {
    return (
      <>
        <div className="flex items-center gap-2">
          <SlotGlyph slotId={headerSlotId} size={18} />
          <h2 className="text-[14px] font-bold text-white">选择 {meta.titleEn} 插件</h2>
        </div>
        <p className="mt-2 text-[12px] leading-snug" style={{ color: "rgba(185,193,208,0.65)" }}>
          {meta.labelZh} · 算法插件
        </p>
      </>
    );
  }
  if (drawerMode === "plugin_config" && meta) {
    return (
      <>
        <div className="flex items-center gap-2">
          <IconSettings size={18} strokeWidth={1.75} style={{ color: "var(--zx-primary)" }} aria-hidden />
          <h2 className="text-[14px] font-bold text-white">{meta.titleEn} 设置</h2>
        </div>
        <p className="mt-2 text-[12px] leading-snug" style={{ color: "rgba(185,193,208,0.65)" }}>
          {meta.labelZh} · 超参数
        </p>
      </>
    );
  }
  if (drawerMode === "idle" && (!headerSlotId || !meta)) {
    return (
      <>
        <h2 className="text-[14px] font-bold text-white">属性面板</h2>
        <p className="mt-2 text-[12px]" style={{ color: "rgba(185,193,208,0.45)" }}>
          在画布中点击流程组件以开始
        </p>
      </>
    );
  }
  if (drawerMode === "idle" && meta && headerSlotId) {
    const a = assignments[headerSlotId];
    return (
      <>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] font-bold leading-snug text-white">
              {meta.titleEn} {meta.labelZh}
            </h2>
            {a ? (
              <p className="mt-2 text-[12px] font-medium leading-snug text-white">{formatAlgorithmLine(a.pluginId, a.pluginTitle)}</p>
            ) : (
              <p className="mt-2 text-[12px] leading-snug" style={{ color: "rgba(185,193,208,0.55)" }}>
                尚未选择算法
              </p>
            )}
          </div>
        </div>
      </>
    );
  }
  return (
    <>
      <h2 className="text-[14px] font-bold text-white">属性面板</h2>
      <p className="mt-2 text-[12px]" style={{ color: "rgba(185,193,208,0.45)" }}>
        未选择节点
      </p>
    </>
  );
}

function BuilderSlotStatusBadge({ slotId }: { slotId: string }) {
  const assignments = useAgentBuilderStore((s) => s.assignments);
  const slotParamValues = useAgentBuilderStore((s) => s.slotParamValues[slotId]);
  const paramsTouched = useAgentBuilderStore((s) => s.slotParamsTouched[slotId] ?? false);
  const a = assignments[slotId];
  const pluginId = a?.pluginId ?? "";
  const groups = pluginId ? getPluginParamGroups(pluginId) : [];
  const hasFields = groups.some((g) => g.fields.length > 0);
  const defaults = pluginId ? getDefaultSlotParamValues(pluginId) : {};
  const merged = { ...defaults, ...(slotParamValues ?? {}) };
  const errs = pluginId ? buildParamValueErrors(pluginId, merged) : {};
  const complete = Boolean(a && pluginId && (!hasFields || (paramsTouched && Object.keys(errs).length === 0)));
  const configuring = Boolean(a && pluginId && !complete);

  if (complete) {
    return (
      <div
        className="flex shrink-0 items-center gap-1 rounded-[4px] px-2 py-0.5 text-[11px] font-semibold text-white"
        style={{ backgroundColor: "var(--zx-primary)" }}
        title="参数已全部配置完成"
      >
        <IconCheck size={12} strokeWidth={2.5} aria-hidden />
        <span>已完成</span>
      </div>
    );
  }
  if (configuring) {
    return (
      <div
        className="shrink-0 rounded-[4px] px-2 py-0.5 text-[11px] font-semibold"
        style={{
          backgroundColor: "rgba(255,255,255,0.08)",
          color: "rgba(185,193,208,0.78)",
        }}
        title="算法已选，参数待完善"
      >
        配置中
      </div>
    );
  }
  return null;
}

export function PropertyDrawer() {
  const location = useLocation();
  const drawerMode = useAgentBuilderStore((s) => s.drawerMode);
  const selectedSlotId = useAgentBuilderStore((s) => s.selectedSlotId);
  const focusedSlotId = useAgentBuilderStore((s) => s.focusedSlotId);
  const assignments = useAgentBuilderStore((s) => s.assignments);
  const openPluginShowcase = useAgentBuilderStore((s) => s.openPluginShowcase);
  const persistSlotParamSnapshot = useAgentBuilderStore((s) => s.persistSlotParamSnapshot);

  const onBuilder = location.pathname.startsWith("/builder");

  const shellHeader = (
    <div className="border-b px-6 py-4" style={{ borderColor: "var(--zx-divider-ui)" }}>
      <h2 className="zx-title">属性面板</h2>
      <p className="zx-muted mt-2">当前模块无侧栏配置</p>
    </div>
  );

  if (!onBuilder) {
    return (
      <aside className={drawerShellDefault} style={{ borderColor: "var(--zx-border-light)" }}>
        {shellHeader}
        <div className="flex min-h-0 flex-1 flex-col">
          <DrawerEmptyState message="选中组件配置参数：请在画布中点击流程卡片" />
        </div>
      </aside>
    );
  }

  const headerSlotId =
    drawerMode === "idle" ? focusedSlotId : selectedSlotId ?? focusedSlotId;
  const meta = headerSlotId ? getSlotMeta(headerSlotId) : null;

  const builderHeaderRow =
    drawerMode === "idle" && headerSlotId && meta ? (
      <div className="flex items-start justify-between gap-2 border-b px-5 py-4" style={{ borderColor: "var(--zx-divider-ui)" }}>
        <div className="min-w-0 flex-1">
          <DrawerHeaderBlock drawerMode="idle" headerSlotId={headerSlotId} meta={meta} assignments={assignments} />
        </div>
        <BuilderSlotStatusBadge slotId={headerSlotId} />
      </div>
    ) : (
      <div className="border-b px-5 py-4" style={{ borderColor: "var(--zx-divider-ui)" }}>
        <DrawerHeaderBlock drawerMode={drawerMode} headerSlotId={headerSlotId} meta={meta} assignments={assignments} />
      </div>
    );

  return (
    <aside className={`${drawerShellBuilder} ${STUDIO_BUILDER_FLOATING_SURFACE_CLASS} pb-4 pt-4 font-sans`}>
      {builderHeaderRow}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {drawerMode === "plugin_showcase" ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <PluginShowcasePanel />
          </div>
        ) : drawerMode === "plugin_config" && headerSlotId ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <BuilderSlotParamsPanel slotId={headerSlotId} />
            </div>
            <div className="shrink-0 border-t px-5 py-4" style={{ borderColor: "var(--zx-divider-ui)" }}>
              <ChromePrimaryButton className="w-full" onClick={() => persistSlotParamSnapshot(headerSlotId)}>
                保存参数
              </ChromePrimaryButton>
            </div>
          </div>
        ) : focusedSlotId && meta ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {assignments[focusedSlotId] ? (
                <BuilderSlotParamsPanel slotId={focusedSlotId} />
              ) : (
                <div className="flex flex-col gap-4">
                  <p className="text-[12px] leading-relaxed" style={{ color: LABEL_COLOR }}>
                    尚未挂载算法。请在画布卡片上选择算法，或点击下方打开插件橱窗。
                  </p>
                  <ChromeSecondaryButton className="w-full" onClick={() => openPluginShowcase(focusedSlotId)}>
                    打开插件橱窗
                  </ChromeSecondaryButton>
                </div>
              )}
            </div>
            {assignments[focusedSlotId] ? (
              <div className="shrink-0 border-t px-5 py-4" style={{ borderColor: "var(--zx-divider-ui)" }}>
                <ChromePrimaryButton className="w-full" onClick={() => persistSlotParamSnapshot(focusedSlotId)}>
                  保存参数
                </ChromePrimaryButton>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center px-5 py-10 text-center">
            <p className="max-w-[240px] text-[13px] leading-relaxed" style={{ color: "rgba(185,193,208,0.45)" }}>
              选中组件配置参数：请先在画布中点击流程卡片
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
