import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { requestModuleSwitch } from "@/domain/nav/requestModuleSwitch";
import { useStudioRegistryStore } from "@/stores/studioRegistryStore";

export type ModuleNavSwitchContextValue = {
  pendingPath: string | null;
  errorPath: string | null;
  switchModule: (path: string) => Promise<void>;
  retry: () => Promise<void>;
};

const ModuleNavSwitchContext = createContext<ModuleNavSwitchContextValue | null>(null);

export function ModuleNavSwitchProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const pathname = useLocation().pathname;
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const [errorPath, setErrorPath] = useState<string | null>(null);
  const errorPathRef = useRef<string | null>(null);
  const abRef = useRef<AbortController | null>(null);

  useEffect(() => {
    errorPathRef.current = errorPath;
  }, [errorPath]);

  const switchModule = useCallback(
    async (target: string) => {
      const normalized = target === "" ? "/" : target;
      if (normalized === "/") {
        if (pathname === "/" || pathname === "") return;
        abRef.current?.abort();
        setErrorPath(null);
        setPendingPath(null);
        navigate("/");
        return;
      }

      if (normalized !== "/builder" && pathname === normalized) return;

      abRef.current?.abort();
      const ac = new AbortController();
      abRef.current = ac;

      setErrorPath(null);
      setPendingPath(normalized);

      try {
        await requestModuleSwitch(normalized, ac.signal);
        if (ac.signal.aborted) return;
        navigate(normalized);
        useStudioRegistryStore.getState().touchModuleConfigForPath(normalized);
      } catch (e) {
        if (ac.signal.aborted) return;
        if (e instanceof DOMException && e.name === "AbortError") return;
        setErrorPath(normalized);
      } finally {
        if (!ac.signal.aborted) {
          setPendingPath(null);
        }
      }
    },
    [navigate, pathname],
  );

  const retry = useCallback(async () => {
    const ep = errorPathRef.current;
    if (!ep) return;
    await switchModule(ep);
  }, [switchModule]);

  const value = useMemo<ModuleNavSwitchContextValue>(
    () => ({ pendingPath, errorPath, switchModule, retry }),
    [pendingPath, errorPath, switchModule, retry],
  );

  return <ModuleNavSwitchContext.Provider value={value}>{children}</ModuleNavSwitchContext.Provider>;
}

export function useModuleNavSwitch(): ModuleNavSwitchContextValue {
  const v = useContext(ModuleNavSwitchContext);
  if (!v) {
    throw new Error("useModuleNavSwitch must be used within ModuleNavSwitchProvider");
  }
  return v;
}
