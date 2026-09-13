import { useEffect, useMemo } from "react";
import type { ReplayEnvelope } from "@/entities/replay";
import { replayDelayMs } from "../lib/playbackTiming";
import {
  replayMilestoneCursors,
  selectFailureTargets,
  type ReplayProjection,
} from "../model/replayProjection";
import { useReplayPlaybackStore, type ReplaySpeed } from "../model/playback.store";
import styles from "./trajectoryReplay.module.css";

type ReplayTimelineProps = {
  envelope: ReplayEnvelope;
  projection: ReplayProjection;
};

/** Drive bounded visual playback and render independent Agent/Benchmark lanes. */
export function ReplayTimeline({ envelope, projection }: ReplayTimelineProps) {
  const cursor = useReplayPlaybackStore((state) => state.cursor);
  const maxCursor = useReplayPlaybackStore((state) => state.maxCursor);
  const playing = useReplayPlaybackStore((state) => state.isPlaying);
  const speed = useReplayPlaybackStore((state) => state.speed);
  const lockedActivationId = useReplayPlaybackStore(
    (state) => state.lockedActivationId,
  );
  const initialize = useReplayPlaybackStore((state) => state.initialize);
  const play = useReplayPlaybackStore((state) => state.play);
  const pause = useReplayPlaybackStore((state) => state.pause);
  const setSpeed = useReplayPlaybackStore((state) => state.setSpeed);
  const seek = useReplayPlaybackStore((state) => state.seek);
  const step = useReplayPlaybackStore((state) => state.step);
  const advance = useReplayPlaybackStore((state) => state.advance);
  const lockActivation = useReplayPlaybackStore((state) => state.lockActivation);
  const selectMoment = useReplayPlaybackStore((state) => state.selectMoment);
  const milestones = useMemo(
    () => replayMilestoneCursors(envelope.moments),
    [envelope.moments],
  );
  const milestoneMoments = useMemo(() => {
    const cursors = new Set(milestones);
    return envelope.moments.filter((moment) => cursors.has(moment.causalIndex));
  }, [envelope.moments, milestones]);
  const failures = selectFailureTargets(projection);

  useEffect(() => {
    initialize(
      envelope.runId,
      envelope.moments.at(-1)?.causalIndex ?? -1,
    );
  }, [envelope.moments, envelope.runId, initialize]);

  useEffect(() => {
    if (!playing || cursor >= maxCursor) return;
    const index = envelope.moments.findIndex((item) => item.causalIndex === cursor);
    const current = index >= 0 ? envelope.moments[index] : undefined;
    const next = index >= 0 ? envelope.moments[index + 1] : envelope.moments[0];
    const timeout = window.setTimeout(advance, replayDelayMs(current, next, speed));
    return () => window.clearTimeout(timeout);
  }, [advance, cursor, envelope.moments, maxCursor, playing, speed]);

  return (
    <section className={styles.timeline} aria-label="Replay timeline">
      <div className={styles.controls}>
        <button type="button" onClick={() => step(milestones, -1)} aria-label="上一个里程碑">‹</button>
        <button
          type="button"
          className={styles.play}
          onClick={() => {
            if (playing) {
              pause();
              return;
            }
            if (cursor >= maxCursor) seek(-1);
            play();
          }}
        >
          {playing ? "暂停" : cursor >= maxCursor ? "重播" : "播放"}
        </button>
        <button type="button" onClick={() => step(milestones, 1)} aria-label="下一个里程碑">›</button>
        <div className={styles.speed}>
          {([0.5, 1, 2] as ReplaySpeed[]).map((item) => (
            <button
              type="button"
              key={item}
              data-active={speed === item}
              onClick={() => setSpeed(item)}
            >
              {item}×
            </button>
          ))}
        </div>
        <span className={styles.cursor}>
          {Math.max(cursor, 0)} / {Math.max(maxCursor, 0)}
        </span>
        {failures[0] ? (
          <button
            type="button"
            className={styles.failureJump}
            onClick={() => {
              seek(failures[0]!.cursor);
              lockActivation(failures[0]!.activationId);
            }}
          >
            跳到失败
          </button>
        ) : null}
      </div>

      {lockedActivationId ? (
        <div className={styles.lockHint}>
          Inspector 已锁定 {lockedActivationId}
          <button type="button" onClick={() => lockActivation(null)}>回到当前节点</button>
        </div>
      ) : null}

      <div className={styles.lane}>
        <div className={styles.laneLabel}>
          <strong>Agent</strong>
          <span>{envelope.result.status}</span>
        </div>
        <div className={styles.milestoneMoments}>
          {milestoneMoments.map((moment) => (
            <button
              type="button"
              key={moment.momentId}
              className={moment.causalIndex <= cursor ? styles.consumed : ""}
              data-kind={moment.kind}
              title={`${moment.causalIndex} · ${moment.nodePath || moment.phase} · ${moment.kind}`}
              onClick={() => {
                seek(moment.causalIndex);
                selectMoment(moment.momentId);
              }}
            >
              <i />
              <span>{moment.nodePath || moment.phase || moment.role || moment.sourceKind}</span>
              <small>{moment.kind}</small>
            </button>
          ))}
        </div>
      </div>

      {envelope.benchmark ? (
        <div className={styles.lane}>
          <div className={styles.laneLabel}>
            <strong>Benchmark</strong>
            <span>{envelope.benchmark.outcome}</span>
          </div>
          <div className={styles.benchmarkPhases}>
            {envelope.benchmark.phases.map((phase) => (
              <span key={phase.phase} data-status={phase.status}>
                {phase.phase} · {phase.status}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <details className={styles.exactMoments}>
        <summary>精确事件 · {envelope.moments.length}</summary>
        <div className={styles.exactMomentList}>
          {envelope.moments.map((moment) => (
            <button
              type="button"
              key={moment.momentId}
              className={moment.causalIndex <= cursor ? styles.consumed : ""}
              onClick={() => {
                seek(moment.causalIndex);
                selectMoment(moment.momentId);
              }}
            >
              <code>{moment.causalIndex}</code>
              <span>{moment.sourceKind}</span>
              <strong>{moment.kind}</strong>
              <small>{moment.nodePath || moment.phase || "—"}</small>
            </button>
          ))}
        </div>
      </details>
    </section>
  );
}
