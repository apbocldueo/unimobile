import { create } from "zustand";

export type StudioThemeMode = "dark" | "light";
export type StudioFontScale = "sm" | "md" | "lg";
export type StudioDefaultModule = "/builder" | "/benchmark" | "/history" | "/settings";

const STORAGE_KEY = "zx-studio-settings-v1";

type Persisted = {
  themeMode: StudioThemeMode;
  fontScale: StudioFontScale;
  defaultModule: StudioDefaultModule;
};

const defaults: Persisted = {
  themeMode: "dark",
  fontScale: "md",
  defaultModule: "/builder",
};

function load(): Persisted {
  if (typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = { ...defaults, ...JSON.parse(raw) } as Persisted;
    if ((parsed as { defaultModule?: string }).defaultModule === "/agent-studio") {
      parsed.defaultModule = "/builder";
    }
    return parsed;
  } catch {
    return defaults;
  }
}

function save(p: Partial<Persisted>) {
  if (typeof window === "undefined") return;
  try {
    const cur = load();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...cur, ...p }));
  } catch {
    /* private mode */
  }
}

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
