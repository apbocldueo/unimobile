import { uiText, useUiLocale } from "@/shared/i18n";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { DEFAULT_PANES, fitPanes, parsePanePreferences, PANE_STORAGE_KEY, type PanePreferences } from "../model/panePreferences";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import styles from "./agentBuilder.module.css";
import { BuilderPanelContext, type InspectorView } from "./BuilderPanelContext";

/** Compose bounded display-only panes; all document state stays with its existing owner.
 * Args: children are the toolbar, palette, canvas and mounted Inspector.
 * Returns: A display-only panel provider and resizable workspace.
 */
export function BuilderLayout({ children }: { children: ReactNode }) {
  useUiLocale();
  const sessionId = useAgentBuilderDocumentStore((state) => state.sessionId);
  const selected = useAgentBuilderDocumentStore((state) => state.selectedCanvasId ?? state.selectedEdgeId);
  const failedValidation = useAgentBuilderDocumentStore((state) => state.compileResult?.isSuccess === false ? state.compileResult : null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [view, setView] = useState<InspectorView>("configuration");
  useEffect(() => { setPaletteOpen(false); setInspectorOpen(false); setView("configuration"); }, [sessionId]);
  useEffect(() => { if (selected) { setInspectorOpen(true); setView("configuration"); } }, [selected]);
  useEffect(() => { if (failedValidation) { setInspectorOpen(true); setView("checks"); } }, [failedValidation]);
  const root = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1024);
  const [preferred, setPreferred] = useState<PanePreferences>(() => {
    try { return parsePanePreferences(localStorage.getItem(PANE_STORAGE_KEY)); } catch { return { ...DEFAULT_PANES }; }
  });
  const drag = useRef<{ pointer: number; side: keyof PanePreferences; startX: number; startWidth: number } | null>(null);
  const panes = fitPanes(width, preferred);
  useEffect(() => {
    const element = root.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => { if (entry) setWidth(entry.contentRect.width); });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    try { localStorage.setItem(PANE_STORAGE_KEY, JSON.stringify({ version: 1, ...preferred })); } catch { /* Storage is optional. */ }
  }, [preferred]);
  /** Bound a user's width preference; layout fitting separately handles narrow windows. */
  const resize = (side: keyof PanePreferences, value: number) => {
    setPreferred((previous) => ({ ...previous, [side]: Math.min(side === "palette" ? 360 : 720, Math.max(side === "palette" ? 140 : 240, value)) }));
  };
  return <BuilderPanelContext.Provider value={{ view, show: (next) => { setView(next); setInspectorOpen(true); }, close: () => setInspectorOpen(false) }}><div ref={root} tabIndex={-1} aria-label="Builder workspace" className={`${styles.workbench} ${!paletteOpen ? styles.paletteClosed : ""} ${!inspectorOpen ? styles.inspectorClosed : ""}`} style={{ gridTemplateColumns: `${paletteOpen ? panes.palette : 0}px ${paletteOpen ? 6 : 0}px minmax(0, 1fr) ${inspectorOpen ? 6 : 0}px ${inspectorOpen ? panes.inspector : 0}px` }}>
    {children}
    <div className={styles.panelSwitches} role="group" aria-label={uiText("编辑面板")}>
      <button type="button" className={styles.button} aria-expanded={paletteOpen} onClick={() => setPaletteOpen(!paletteOpen)}>{paletteOpen ? uiText("收起能力库") : uiText("＋ 添加能力")}</button>
      <button type="button" className={styles.button} aria-expanded={inspectorOpen} onClick={() => setInspectorOpen(!inspectorOpen)}>{inspectorOpen ? uiText("收起配置") : uiText("配置与检查")}</button>
    </div>
    {(["palette", "inspector"] as const).filter((side) => side === "palette" ? paletteOpen : inspectorOpen).map((side) => <div key={side} role="separator" tabIndex={0} aria-label={`Resize ${side}`} aria-orientation="vertical"
      aria-valuemin={0} aria-valuemax={Math.round(width)} aria-valuenow={panes[side]}
      className={`${styles.paneSeparator} ${side === "palette" ? styles.paletteSeparator : styles.inspectorSeparator}`}
      onKeyDown={(event) => {
        if (event.key === "Home") { event.preventDefault(); setPreferred({ ...DEFAULT_PANES }); }
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        resize(side, panes[side] + (event.key === "ArrowRight" ? 20 : -20) * (side === "palette" ? 1 : -1));
      }}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { pointer: event.pointerId, side, startX: event.clientX, startWidth: panes[side] };
      }}
      onPointerMove={(event) => {
        const current = drag.current;
        if (current?.pointer !== event.pointerId || current.side !== side) return;
        resize(side, current.startWidth + (event.clientX - current.startX) * (side === "palette" ? 1 : -1));
      }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} />)}

  </div></BuilderPanelContext.Provider>;
}
