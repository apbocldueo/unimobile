import { useCallback, useEffect, useMemo, useState } from "react";
import { useModuleNavSwitch } from "@/app/shell/ModuleNavSwitchContext";
import { AGENT_STUDIO_FLOW_PRESETS } from "@/features/agent-studio/flowPresetDocuments";
import { setStudioBuilderPendingFlowDocument } from "@/features/agent-studio/studioBuilderPendingFlow";
import type { FlowDocumentV1 } from "@/modules/flow-graph/flowDocument";
import {
  fetchStudioFlowTemplateDocument,
  fetchStudioFlowTemplates,
  type StudioFlowTemplateListItemDTO,
} from "@/services/studioFlowTemplatesClient";
import { getStudioApiBase } from "@/services/studioRegistryClient";
import { useToastStore } from "@/stores/toastStore";
import { IconBot, IconLayers } from "@/components/icons/StudioIcons";

const MODAL_TITLE = "ZhiXing Studio · 兵工厂";
const MODAL_LEAD = "选择预设模板进入画布，或创建空白流程后自行拖拽搭建。";

const templateCardBase =
  "flex w-full flex-col gap-1 rounded-lg border px-3.5 py-3 text-left outline-none transition-[border-color,background-color,box-shadow,transform] duration-150 focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-panel)]";

const templateCardStyle =
  "border-[color:var(--zx-border-light)] bg-[rgba(40,40,40,0.55)] hover:border-[color:var(--zx-primary-border)] hover:bg-[rgba(60,60,60,0.82)] focus-visible:border-[color:var(--zx-primary-border)] active:scale-[0.99] disabled:pointer-events-none disabled:opacity-50";

type Props = {
  onClose: () => void;
};

type TemplateRow =
  | (StudioFlowTemplateListItemDTO & { source: "remote" })
  | { source: "local"; id: string; name: string; description: string; build: () => FlowDocumentV1 };

/**
 * 兵工厂入口弹窗：
 * - 有 Studio API 时：预设列表与文档由后端 ``/studio/flow-templates`` 与 ``manifest.yaml`` 驱动；
 * - 无 API 或列表失败时：回退到内置 ``AGENT_STUDIO_FLOW_PRESETS``（便于离线开发）。
 */
export function StudioHomeArmoryEntryModal({ onClose }: Props) {
  const { switchModule } = useModuleNavSwitch();
  const pushToast = useToastStore((s) => s.pushToast);

  const [remoteTemplates, setRemoteTemplates] = useState<StudioFlowTemplateListItemDTO[] | null>(null);
  /** 有 Studio API 时首帧即视为加载中，避免先闪一下内置预设再切到远端列表。 */
  const [remoteLoading, setRemoteLoading] = useState(() => Boolean(getStudioApiBase()));
  const [remoteError, setRemoteError] = useState<string | null>(null);
  const [pickBusyId, setPickBusyId] = useState<string | null>(null);

  const emptyPreset = useMemo(() => AGENT_STUDIO_FLOW_PRESETS.find((p) => p.id === "empty"), []);

  useEffect(() => {
    const base = getStudioApiBase();
    if (!base) {
      setRemoteTemplates(null);
      setRemoteError(null);
      setRemoteLoading(false);
      return;
    }
    let cancelled = false;
    setRemoteLoading(true);
    setRemoteError(null);
    void fetchStudioFlowTemplates()
      .then((rows) => {
        if (cancelled) return;
        setRemoteTemplates(rows);
      })
      .catch((e) => {
        if (cancelled) return;
        setRemoteTemplates(null);
        setRemoteError(e instanceof Error ? e.message : "flow_templates_failed");
      })
      .finally(() => {
        if (!cancelled) setRemoteLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const templateRows: TemplateRow[] = useMemo(() => {
    const base = getStudioApiBase();
    const localRows: TemplateRow[] = AGENT_STUDIO_FLOW_PRESETS.filter((p) => p.id !== "empty").map((p) => ({
      source: "local" as const,
      id: p.id,
      name: p.name,
      description: p.description,
      build: p.build,
    }));
    if (!base) return localRows;
    if (remoteLoading) return [];
    if (remoteError) return localRows;
    if (remoteTemplates !== null) {
      return remoteTemplates.map((t) => ({ ...t, source: "remote" as const }));
    }
    return localRows;
  }, [remoteError, remoteLoading, remoteTemplates]);

  const goBuilderWithDoc = useCallback(
    (doc: FlowDocumentV1) => {
      setStudioBuilderPendingFlowDocument(doc);
      void switchModule("/builder");
      onClose();
    },
    [onClose, switchModule],
  );

  const onPickRemote = useCallback(
    async (id: string) => {
      setPickBusyId(id);
      try {
        const doc = await fetchStudioFlowTemplateDocument(id);
        goBuilderWithDoc(doc);
      } catch (e) {
        pushToast({
          message: e instanceof Error ? e.message : "加载模板失败",
          tone: "error",
          durationMs: 5200,
        });
      } finally {
        setPickBusyId(null);
      }
    },
    [goBuilderWithDoc, pushToast],
  );

  const onPickLocal = useCallback(
    (build: () => FlowDocumentV1) => {
      goBuilderWithDoc(build());
    },
    [goBuilderWithDoc],
  );

  const onBlank = useCallback(() => {
    if (!emptyPreset) return;
    goBuilderWithDoc(emptyPreset.build());
  }, [emptyPreset, goBuilderWithDoc]);

  const showRemoteEmptyHint =
    Boolean(getStudioApiBase()) &&
    !remoteLoading &&
    !remoteError &&
    remoteTemplates !== null &&
    remoteTemplates.length === 0;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 font-sans" role="presentation">
      <button type="button" className="absolute inset-0 bg-black/60 backdrop-blur-[2px]" aria-label="关闭" onClick={onClose} />
      <div
        className="relative z-[1] flex max-h-[min(90dvh,640px)] w-full max-w-[520px] flex-col overflow-hidden rounded-xl border shadow-[var(--zx-shadow-soft)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="zx-armory-entry-title"
        style={{
          backgroundColor: "var(--zx-panel)",
          borderColor: "var(--zx-border-light)",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="shrink-0 border-b border-white/[0.06] px-5 py-4">
          <h2 id="zx-armory-entry-title" className="text-[16px] font-semibold tracking-tight text-white">
            {MODAL_TITLE}
          </h2>
          <p className="mt-2 text-[13px] leading-relaxed text-[color:var(--zx-text-muted)]">{MODAL_LEAD}</p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <section aria-labelledby="zx-armory-templates-heading">
            <h3 id="zx-armory-templates-heading" className="text-[11px] font-semibold uppercase tracking-wider text-[color:var(--zx-text-muted)]">
              预设模板
            </h3>
            {remoteError ? (
              <p className="mt-2 text-[12px] leading-relaxed text-[color:var(--zx-text-muted)] opacity-90">
                无法加载后端模板列表（{remoteError}），已使用内置预设。
              </p>
            ) : null}
            {remoteLoading ? (
              <p className="mt-3 text-[12px] text-[color:var(--zx-text-muted)]">正在加载模板…</p>
            ) : null}
            {showRemoteEmptyHint ? (
              <p className="mt-2 text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
                后端未配置任何模板（可在仓库内编辑 zhixing/studio/data/flow_templates/manifest.yaml）。
              </p>
            ) : null}
            <div className="mt-3 flex flex-col gap-2">
              {templateRows.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  disabled={pickBusyId !== null}
                  className={[templateCardBase, templateCardStyle].join(" ")}
                  onClick={() =>
                    row.source === "remote" ? void onPickRemote(row.id) : onPickLocal(row.build)
                  }
                >
                  <span className="flex items-start gap-3">
                    <span
                      className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-black/30 text-[#7eb8ff]"
                      aria-hidden
                    >
                      <IconLayers size={18} strokeWidth={1.85} className="text-current" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[14px] font-semibold leading-snug text-white">
                        {row.name}
                        {pickBusyId === row.id ? (
                          <span className="ml-2 inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />
                        ) : null}
                      </span>
                      <span className="mt-1 block text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">{row.description}</span>
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section className="mt-8" aria-labelledby="zx-armory-custom-heading">
            <h3 id="zx-armory-custom-heading" className="text-[11px] font-semibold uppercase tracking-wider text-[color:var(--zx-text-muted)]">
              自定义
            </h3>
            <button
              type="button"
              disabled={pickBusyId !== null}
              className={[templateCardBase, "mt-3 items-stretch", templateCardStyle].join(" ")}
              onClick={onBlank}
            >
              <span className="flex items-start gap-3">
                <span
                  className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-black/30 text-[#7eb8ff]"
                  aria-hidden
                >
                  <IconBot size={18} strokeWidth={1.85} className="text-current" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[14px] font-semibold leading-snug text-white">空白流程</span>
                  <span className="mt-1 block text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
                    无预置节点，进入画布后从左侧拖拽组件搭建
                  </span>
                </span>
              </span>
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}
