import { createContext, useContext, useState } from "react";

export type InspectorView = "configuration" | "checks";
export type BuilderPanels = {
  view: InspectorView;
  show: (view: InspectorView) => void;
  close?: () => void;
};

export const BuilderPanelContext = createContext<BuilderPanels | null>(null);

/** Share disposable panel navigation, with a local fallback for isolated surfaces.
 * Returns: The active view and navigation commands; never writes document state.
 */
export function useBuilderPanels(): BuilderPanels {
  const context = useContext(BuilderPanelContext);
  const [view, show] = useState<InspectorView>("configuration");
  return context ?? { view, show };
}
