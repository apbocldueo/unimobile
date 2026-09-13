import { useRef, useState, type PointerEvent, type ReactNode } from "react";
import styles from "./threePaneReplayWorkbench.module.css";

export type PanePreference = {
  left: number;
  middle: number;
  right: number;
};

type ThreePaneWorkbenchLayoutProps = {
  header: ReactNode;
  banner?: ReactNode;
  left: ReactNode;
  middle: ReactNode;
  right: ReactNode;
  footer?: ReactNode;
  defaultPanes?: PanePreference;
  compactMiddle?: boolean;
  compactPanes?: PanePreference;
};

const DEFAULT_PANES: PanePreference = { left: 42, middle: 25, right: 33 };
const COMPACT_REPLAY_PANES: PanePreference = { left: 58, middle: 12, right: 30 };
const PANE_STORAGE_KEY = "zx-studio-workbench-panes-v3";
const LEGACY_PANE_STORAGE_KEYS = [
  "zx-studio-workbench-panes-v2",
  "zx-studio-replay-panes-v1",
];

/** Validate one non-semantic pane preference against usable minimum widths. */
function parsePanePreference(raw: string | null): PanePreference | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PanePreference>;
    if (
      typeof value.left === "number"
      && typeof value.middle === "number"
      && typeof value.right === "number"
      && value.left >= 24
      && value.middle >= 10
      && value.right >= 18
      && value.left + value.middle + value.right >= 95
      && value.left + value.middle + value.right <= 105
    ) {
      return {
        left: value.left,
        middle: value.middle,
        right: value.right,
      };
    }
  } catch {
    return null;
  }
  return null;
}

/** Read a persisted preference and migrate legacy presentation-only keys. */
function readStoredPanePreference(): PanePreference | null {
  if (typeof window === "undefined") return null;
  const current = parsePanePreference(window.localStorage.getItem(PANE_STORAGE_KEY));
  if (current) return current;
  for (const key of LEGACY_PANE_STORAGE_KEYS) {
    const legacy = parsePanePreference(window.localStorage.getItem(key));
    if (legacy) {
      try {
        window.localStorage.setItem(PANE_STORAGE_KEY, JSON.stringify(legacy));
      } catch {
        // Preference migration is optional in restricted browser contexts.
      }
      return legacy;
    }
  }
  return null;
}

/** Read and migrate the shared pane preference without storing Run evidence. */
export function readPanePreference(
  fallback: PanePreference = DEFAULT_PANES,
): PanePreference {
  return readStoredPanePreference() ?? fallback;
}

/** Persist only pane geometry, never task, event, or artifact evidence. */
function savePanePreference(value: PanePreference): void {
  try {
    window.localStorage.setItem(PANE_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Private browsing can disable localStorage without affecting the workbench.
  }
}

/** Clear pane geometry only, leaving all Replay facts untouched. */
export function resetPanePreference(): void {
  try {
    window.localStorage.removeItem(PANE_STORAGE_KEY);
    for (const key of LEGACY_PANE_STORAGE_KEYS) {
      window.localStorage.removeItem(key);
    }
  } catch {
    // A blocked localStorage does not affect Replay evidence or navigation.
  }
}

/** Compose a mode-neutral bounded three-pane research workbench. */
export function ThreePaneWorkbenchLayout({
  header,
  banner,
  left,
  middle,
  right,
  footer,
  defaultPanes = DEFAULT_PANES,
  compactMiddle = false,
  compactPanes = COMPACT_REPLAY_PANES,
}: ThreePaneWorkbenchLayoutProps) {
  const container = useRef<HTMLDivElement>(null);
  const storedAtMount = useRef<PanePreference | null>(readStoredPanePreference());
  const [hasCustomPanes, setHasCustomPanes] = useState(storedAtMount.current !== null);
  const [panes, setPanes] = useState(
    () => storedAtMount.current ?? defaultPanes,
  );
  const visiblePanes = hasCustomPanes
    ? panes
    : compactMiddle
      ? compactPanes
      : defaultPanes;

  /** Begin one bounded two-pane resize and persist only on pointer release. */
  const startResize = (
    boundary: "left-middle" | "middle-right",
    event: PointerEvent<HTMLDivElement>,
  ) => {
    event.preventDefault();
    const initial = visiblePanes;
    const startX = event.clientX;
    const width = container.current?.getBoundingClientRect().width ?? 1;
    const move = (pointer: globalThis.PointerEvent) => {
      const delta = ((pointer.clientX - startX) / width) * 100;
      setPanes(() => {
        if (boundary === "left-middle") {
          const left = Math.min(61, Math.max(24, initial.left + delta));
          const middle = Math.min(
            46,
            Math.max(17, initial.middle - (left - initial.left)),
          );
          return {
            left: initial.left + (initial.middle - middle),
            middle,
            right: initial.right,
          };
        }
        const middle = Math.min(46, Math.max(17, initial.middle + delta));
        const right = Math.min(
          52,
          Math.max(22, initial.right - (middle - initial.middle)),
        );
        return {
          left: initial.left,
          middle: initial.middle + (initial.right - right),
          right,
        };
      });
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      setPanes((current) => {
        savePanePreference(current);
        return current;
      });
      setHasCustomPanes(true);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  return (
    <div className={styles.workbench}>
      {header}
      {banner}
      <div
        ref={container}
        className={styles.panes}
        style={{
          gridTemplateColumns: `${visiblePanes.left}fr 6px ${visiblePanes.middle}fr 6px ${visiblePanes.right}fr`,
        }}
      >
        <button
          type="button"
          className={styles.paneReset}
          onClick={() => {
            resetPanePreference();
            setPanes(defaultPanes);
            setHasCustomPanes(false);
          }}
        >
          重置布局
        </button>
        <div className={styles.pane}>{left}</div>
        <div
          className={styles.resizer}
          role="separator"
          aria-label="调整 Graph 与手机宽度"
          onPointerDown={(event) => startResize("left-middle", event)}
        />
        <div className={styles.pane}>{middle}</div>
        <div
          className={styles.resizer}
          role="separator"
          aria-label="调整手机与 Inspector 宽度"
          onPointerDown={(event) => startResize("middle-right", event)}
        />
        <div className={styles.pane}>{right}</div>
      </div>
      {footer}
    </div>
  );
}
