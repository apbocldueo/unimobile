import { create } from "zustand";

export type StudioThemeMode = "dark" | "light";
export type StudioFontScale = "sm" | "md" | "lg";
export type StudioDefaultModule = "/" | "/agents" | "/benchmarks" | "/history" | "/settings";

const STORAGE_KEY = "zx-studio-settings-v1";

type Persisted = {
  themeMode: StudioThemeMode;
  fontScale: StudioFontScale;
  defaultModule: StudioDefaultModule;
};

const defaults: Persisted = {
  themeMode: "light",
  fontScale: "md",
  defaultModule: "/",
};

/** Load bounded display preferences while migrating legacy module vocabulary. */
function load(): Persisted {
  if (typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = { ...defaults, ...JSON.parse(raw) } as Persisted;
    const legacyModule = (parsed as { defaultModule?: string }).defaultModule;
    if (legacyModule === "/agent-studio" || legacyModule === "/builder") {
      parsed.defaultModule = "/agents";
    }
    if (legacyModule === "/benchmark") {
      parsed.defaultModule = "/benchmarks";
    }
    if (!["/", "/agents", "/benchmarks", "/history", "/settings"].includes(parsed.defaultModule)) {
      parsed.defaultModule = "/";
    }
    return parsed;
  } catch {
    return defaults;
  }
}

/** Persist only local presentation preferences, never runtime truth. */
function save(p: Partial<Persisted>) {
  if (typeof window === "undefined") return;
  try {
    const cur = load();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...cur, ...p }));
  } catch {
    /* private mode */
  }
}

/** Apply validated presentation preferences to the root element. */
function applyDom({ themeMode, fontScale }: Pick<Persisted, "themeMode" | "fontScale">) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.zxTheme = themeMode;
  root.dataset.zxFont = fontScale;
}

type StudioSettingsState = Persisted & {
  setThemeMode: (m: StudioThemeMode) => void;
  setFontScale: (s: StudioFontScale) => void;
  setDefaultModule: (p: StudioDefaultModule) => void;
  applyDomFromState: () => void;
};

const initial = load();

export const useStudioSettingsStore = create<StudioSettingsState>((set, get) => ({
  ...initial,

  setThemeMode: (m) => {
    save({ themeMode: m });
    set({ themeMode: m });
    applyDom({ themeMode: m, fontScale: get().fontScale });
  },

  setFontScale: (s) => {
    save({ fontScale: s });
    set({ fontScale: s });
    applyDom({ themeMode: get().themeMode, fontScale: s });
  },

  setDefaultModule: (p) => {
    save({ defaultModule: p });
    set({ defaultModule: p });
  },

  applyDomFromState: () => {
    const { themeMode, fontScale } = get();
    applyDom({ themeMode, fontScale });
  },
}));

/** 首屏同步（在 React 挂载前也可调用） */
export function hydrateStudioSettingsDom() {
  const s = load();
  useStudioSettingsStore.setState(s);
  applyDom({ themeMode: s.themeMode, fontScale: s.fontScale });
}
