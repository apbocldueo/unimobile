import type { ReplayAction } from "@/entities/replay";
import type { PhoneFrameProjection } from "@/entities/run";
import { useEffect, useState } from "react";
import styles from "./virtualPhone.module.css";
import type { DevicePaneState } from "../model/devicePaneState";

export type PhoneArtifactResolution = {
  url: string;
  availability: string;
};

type VirtualPhoneProps = {
  frame: PhoneFrameProjection;
  latestAction: ReplayAction | null;
  resolveArtifact: (artifactId: string) => PhoneArtifactResolution | null;
  modeLabel?: string;
  compact?: boolean;
  unavailableDetail?: string;
  deviceState?: DevicePaneState;
};

const FRAME_LABELS: Record<PhoneFrameProjection["state"], string> = {
  available: "当前截图",
  stale: "历史截图 · 等待当前交互证据",
  pending: "尚未到达截图证据",
  missing: "当前截图缺失",
  not_captured: "未采集截图",
  corrupt: "截图证据损坏",
};

/** Render one causal, read-only phone frame without controlling a device. */
export function VirtualPhone({
  frame,
  latestAction,
  resolveArtifact,
  modeLabel = "EVIDENCE STATE",
  compact = false,
  unavailableDetail = "没有当前可读截图；Replay 不会用历史画面冒充当前证据。",
  deviceState,
}: VirtualPhoneProps) {
  const [failedArtifactId, setFailedArtifactId] = useState<string | null>(null);
  useEffect(() => {
    setFailedArtifactId(null);
  }, [frame.screenshotArtifactId]);
  const screenshot = frame.screenshotArtifactId
    ? resolveArtifact(frame.screenshotArtifactId)
    : undefined;
  const displayState =
    frame.screenshotArtifactId !== null
    && failedArtifactId === frame.screenshotArtifactId
      ? "corrupt"
      : frame.state;
  const canRender =
    frame.screenshotArtifactId !== null
    && screenshot?.availability === "available"
    && failedArtifactId !== frame.screenshotArtifactId;
  if (compact || !canRender) {
    return (
      <section className={styles.compactShell} aria-label="Virtual Phone">
        <div className={styles.compactIcon} aria-hidden>
          {displayState === "corrupt" ? "!" : "◫"}
        </div>
        <div className={styles.compactCopy}>
          <p className={styles.eyebrow}>DEVICE EVIDENCE · {deviceState?.label ?? modeLabel}</p>
          <h2>{deviceState?.title ?? FRAME_LABELS[displayState]}</h2>
          <p>{deviceState?.detail ?? unavailableDetail}</p>
        </div>
        <dl className={styles.compactFacts}>
          <div>
            <dt>交互</dt>
            <dd>{frame.observation?.interactionStep ?? "—"}</dd>
          </div>
          <div>
            <dt>最近动作</dt>
            <dd>{latestAction ? `${latestAction.actionType} · ${latestAction.status}` : "—"}</dd>
          </div>
        </dl>
      </section>
    );
  }
  return (
    <section className={styles.shell} aria-label="Virtual Phone">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>VIRTUAL PHONE · {modeLabel}</p>
          <h2>设备证据</h2>
        </div>
        <span className={`${styles.state} ${styles[displayState]}`}>
          {FRAME_LABELS[displayState]}
        </span>
      </header>

      <div className={styles.phone}>
        <div className={styles.speaker} />
        <div className={styles.screen}>
          {frame.screenshotArtifactId ? (
            <img
              src={screenshot?.url}
              alt={`Observation ${frame.observation?.observationId ?? ""}`}
              onError={() => setFailedArtifactId(frame.screenshotArtifactId)}
            />
          ) : null}
          {frame.observation?.overlay.map((overlay, index) => {
            if (
              typeof overlay !== "object"
              || overlay === null
              || Array.isArray(overlay)
            ) {
              return null;
            }
            const x = typeof overlay.x === "number" ? overlay.x : null;
            const y = typeof overlay.y === "number" ? overlay.y : null;
            const width = typeof overlay.width === "number" ? overlay.width : null;
            const height = typeof overlay.height === "number" ? overlay.height : null;
            if (x === null || y === null || width === null || height === null) return null;
            return (
              <span
                key={`${x}-${y}-${index}`}
                className={styles.overlay}
                style={{
                  left: `${x * 100}%`,
                  top: `${y * 100}%`,
                  width: `${width * 100}%`,
                  height: `${height * 100}%`,
                }}
              />
            );
          })}
        </div>
        <div className={styles.homeIndicator} />
      </div>

      <dl className={styles.facts}>
        <div>
          <dt>Observation</dt>
          <dd>{frame.observation?.observationId ?? "—"}</dd>
        </div>
        <div>
          <dt>Interaction</dt>
          <dd>{frame.observation?.interactionStep ?? "—"}</dd>
        </div>
        <div>
          <dt>Device</dt>
          <dd>{frame.observation?.deviceId || "not captured"}</dd>
        </div>
        <div>
          <dt>最近 Action</dt>
          <dd>
            {latestAction
              ? `${latestAction.actionType} · ${latestAction.status}`
              : "—"}
          </dd>
        </div>
      </dl>
    </section>
  );
}
