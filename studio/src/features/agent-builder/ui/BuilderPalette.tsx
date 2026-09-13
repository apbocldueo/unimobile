import type { CapabilityFamily, ComponentCatalog } from "@/entities/component-catalog";
import { BUILDER_DRAG_MIME, nextNodePosition } from "../model/flowAdapter";
import { createCapabilityNode } from "../model/nodeFactory";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import styles from "./agentBuilder.module.css";

type BuilderPaletteProps = { catalog: ComponentCatalog | null; loading: boolean; error: string | null };

function startDrag(event: React.DragEvent, family: CapabilityFamily): void {
  event.dataTransfer.setData(BUILDER_DRAG_MIME, JSON.stringify({ type: "capability", family }));
  event.dataTransfer.effectAllowed = "copy";
}

/** Render only backend-authoritative core and approved capability families. */
export function BuilderPalette({ catalog, loading, error }: BuilderPaletteProps) {
  const addNode = useAgentBuilderDocumentStore((state) => state.addNode);
  const selectNode = useAgentBuilderDocumentStore((state) => state.selectNode);
  const addFamily = (family: CapabilityFamily) => {
    const state = useAgentBuilderDocumentStore.getState();
    if (!state.document || !catalog) return;
    const node = createCapabilityNode(family, catalog, state.document);
    const position = nextNodePosition(state.document.capabilities.length + 2);
    addNode(node, {
      ...position,
      label: catalog.capabilityFamilies?.find((item) => item.family === family)?.label ?? family,
      description: `${family} capability`,
      icon: "",
      collapsed: false,
      renderMode: "card",
    });
    selectNode(node.canvasId);
  };
  return (
    <aside className={styles.palette} aria-label="Agent 能力库">
      <div className={styles.panelHeading}>
        <div><h2>Capabilities</h2><p>六类核心能力与框架批准的独立扩展</p></div>
        {catalog ? <span className={styles.countBadge}>{catalog.capabilityFamilies?.length ?? 0}</span> : null}
      </div>
      {loading ? <p className={styles.muted}>正在加载 Catalog…</p> : null}
      {error ? <p className={styles.errorText}>{error}</p> : null}
      {!catalog && !loading ? <p className={styles.callout}>Catalog 不可用，能力新增与连线已禁用。</p> : null}
      {catalog ? [false, true].map((extension) => {
        const families = (catalog.capabilityFamilies ?? []).filter((item) => item.extension === extension);
        return (
          <section key={String(extension)} className={styles.paletteSection}>
            <h3>{extension ? "Approved extensions" : "Core capabilities"}</h3>
            <div className={styles.paletteGrid}>
              {families.map((item) => {
                const available = item.availableImplementationCount > 0;
                return (
                  <button
                    key={item.family}
                    type="button"
                    draggable={available}
                    disabled={!available}
                    className={styles.paletteCard}
                    onDragStart={(event) => startDrag(event, item.family)}
                    onClick={() => addFamily(item.family)}
                    title={available ? `${item.availableImplementationCount} 个可用实现` : "当前没有可用实现"}
                  >
                    <span className={styles.paletteIcon}>◆</span>
                    <span><strong>{item.label}</strong><small>{item.availableImplementationCount} implementations</small></span>
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
