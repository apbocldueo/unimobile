export type PanePreferences = { palette: number; inspector: number };
export const DEFAULT_PANES: PanePreferences = { palette: 220, inspector: 360 };
export const PANE_STORAGE_KEY = "zx-builder-panes-v1";

/** Validate untrusted preferences; only finite display widths may be restored.
 * Args: raw is localStorage text, never an Agent document.
 * Returns: Bounded preferences or defaults. Malformed JSON does not throw.
 */
export function parsePanePreferences(raw: string | null): PanePreferences {
  try {
    const value = JSON.parse(raw ?? "null");
    if (value?.version !== 1 || !Number.isFinite(value.palette) || !Number.isFinite(value.inspector)) return { ...DEFAULT_PANES };
    return { palette: Math.min(360, Math.max(140, value.palette)), inspector: Math.min(720, Math.max(240, value.inspector)) };
  } catch { return { ...DEFAULT_PANES }; }
}

/** Fit preferred side panes to measured space without changing graph coordinates.
 * Args: width is the available workbench width; preferred contains safe widths.
 * Returns: Actual widths reserving canvas space and both separators.
 */
export function fitPanes(width: number, preferred: PanePreferences): PanePreferences {
  const available = Math.max(0, width - 12);
  const canvas = Math.min(320, available * 0.34);
  const budget = available - canvas;
  const palette = Math.min(preferred.palette, Math.max(0, budget - Math.min(260, budget * 0.62)), available * 0.28);
  return { palette: Math.round(palette), inspector: Math.round(Math.min(preferred.inspector, budget - palette)) };
}
