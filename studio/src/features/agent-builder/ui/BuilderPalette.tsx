import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { useState } from "react";
import { capabilityPurpose } from "../model/builderPresentation";
import type { CapabilityFamily, ComponentCatalog } from "@/entities/component-catalog";
import { BUILDER_DRAG_MIME } from "../model/flowAdapter";
import { useToastStore } from "@/stores/toastStore";
import { useCanvasInteractionStore } from "../model/canvasInteraction.store";
import { createCapabilityNode } from "../model/nodeFactory";
import { palettePortPreview } from "../model/palettePreview";
import { portLabel } from "../model/portPresentation";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import styles from "./agentBuilder.module.css";

type BuilderPaletteProps = { catalog: ComponentCatalog | null; loading: boolean; error: string | null };

/** Transfer only the Catalog family identity to the canvas drop boundary. */
function startDrag(event: React.DragEvent, family: CapabilityFamily): void {
  event.dataTransfer.setData(BUILDER_DRAG_MIME, JSON.stringify({ type: "capability", family }));
  event.dataTransfer.effectAllowed = "copy";
}

/** Render only backend-authoritative core and approved capability families. */
export function BuilderPalette({ catalog, loading, error }: BuilderPaletteProps) {
  useUiLocale();
  const [search, setSearch] = useState("");
  const addNode = useAgentBuilderDocumentStore((state) => state.addNode);
  /** Place a Catalog node in this session's measured canvas or explain the gate. */
  const addFamily = (family: CapabilityFamily) => {
    const state = useAgentBuilderDocumentStore.getState();
    if (!state.document || !catalog) return;
    const port = useCanvasInteractionStore.getState().port;
    const position = port?.sessionId === state.sessionId ? port.placement() : null;
    if (!position) {
      useToastStore.getState().pushToast({ message: "Canvas is not ready. Expand the workspace and try again.", tone: "warning" });
      return;
    }
    const node = createCapabilityNode(family, catalog, state.document);
    addNode(node, {
      ...position,
      label: catalog.capabilityFamilies?.find((item) => item.family === family)?.label ?? family,
      description: `${family} capability`,
      icon: "",
      collapsed: false,
      renderMode: "card",
    });
    port?.reveal(node.canvasId);
  };
  return (
    <aside className={styles.palette} aria-label={uiText("Agent 能力库")}>
      <div className={styles.panelHeading}>
        <div>
          <h2>{uiText("能力库")}</h2>
          <p>{uiText("点击添加，或拖到画布")}</p>
        </div>
        {catalog ? <span className={styles.countBadge}>{catalog.capabilityFamilies?.length ?? 0}</span> : null}
      </div>
      <input className={styles.paletteSearch} aria-label={uiText("搜索能力")} placeholder={uiText("搜索能力名称或用途")} value={search} onChange={(event) => setSearch(event.target.value)} />
      {loading ? <p className={styles.muted}>{uiText("正在加载 Catalog…")}</p> : null}
      {error ? <p className={styles.errorText}>{error}</p> : null}
      {!catalog && !loading ? <p className={styles.callout}>{uiText("Catalog 不可用，能力新增与连线已禁用。")}</p> : null}
      {catalog && search.trim() && !(catalog.capabilityFamilies ?? []).some((item) => `${item.label} ${capabilityPurpose[item.family]}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) ? <p className={styles.muted}>{uiText("没有匹配的能力，试试“屏幕”或“动作”。")}</p> : null}
      {catalog ? [false, true].map((extension) => {
        const families = (catalog.capabilityFamilies ?? []).filter((item) => item.extension === extension && `${item.label} ${capabilityPurpose[item.family]}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
        return (
          <section key={String(extension)} className={styles.paletteSection}>
            <h3>{extension ? uiText("扩展能力") : uiText("基础能力")}</h3>
            <div className={styles.paletteGrid}>
              {families.map((item) => {
                const available = item.availableImplementationCount > 0;
                const preview = palettePortPreview(catalog, item.family);
                const previewText = (ports: typeof preview.inputs) => ports.length ? ports.map((port) => portLabel(port.id)).join("、") : uiText("无");
                return (
                  <button
                    key={item.family}
                    type="button"
                    draggable={available}
                    disabled={!available}
                    className={styles.paletteCard}
                    onDragStart={(event) => startDrag(event, item.family)}
                    onClick={() => addFamily(item.family)}
                    aria-label={uiMessage`添加 ${item.label} 到画布；接收 ${previewText(preview.inputs)}；输出 ${previewText(preview.outputs)}`}
                    title={available ? uiMessage`${item.availableImplementationCount} 个可用实现` : uiText("当前没有可用实现")}
                  >
                    <span className={styles.paletteIcon}>◆</span>
                    <span>
                      <strong>{item.label}</strong>
                      <small>{capabilityPurpose[item.family]}</small>

                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        );
      }) : null}
    </aside>
  );
}
