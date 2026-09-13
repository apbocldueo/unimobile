import { useEffect, useRef, useState } from "react";
import type { DebugEvidenceReference } from "@/entities/run";
import styles from "./runInspector.module.css";

type ModelResponseEvidenceViewerProps = {
  reference: DebugEvidenceReference | null;
  availability: string;
  loadText: ((artifactId: string) => Promise<string>) | null;
};

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; text: string }
  | { kind: "error"; message: string };

/** Lazily load one typed model-response artifact without ordinal fallback. */
export function ModelResponseEvidenceViewer({
  reference,
  availability,
  loadText,
}: ModelResponseEvidenceViewerProps) {
  const [state, setState] = useState<LoadState>({ kind: "idle" });
  const requestGeneration = useRef(0);
  useEffect(() => {
    requestGeneration.current += 1;
    setState({ kind: "idle" });
    return () => {
      requestGeneration.current += 1;
    };
  }, [reference?.artifactId]);

  const load = async () => {
    if (!reference?.artifactId || !loadText) return;
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    setState({ kind: "loading" });
    try {
      const text = await loadText(reference.artifactId);
      if (requestGeneration.current !== generation) return;
      setState({ kind: "loaded", text });
    } catch (error) {
      if (requestGeneration.current !== generation) return;
      setState({
        kind: "error",
        message: error instanceof Error ? error.message : "模型响应读取失败",
      });
    }
  };

  return (
    <div className={styles.modelEvidence}>
      <div className={styles.availability}>
        <span>完整模型响应</span>
        <strong data-state={availability}>{availability}</strong>
      </div>
      {reference?.artifactId && loadText ? (
        <>
          <button
            type="button"
            className={styles.returnButton}
            disabled={state.kind === "loading"}
            onClick={() => void load()}
          >
            {state.kind === "loading" ? "正在读取…" : "加载完整响应"}
          </button>
          {state.kind === "loaded" ? (
            <pre className={styles.json}>{state.text}</pre>
          ) : null}
          {state.kind === "error" ? (
            <p className={styles.error}>{state.message}</p>
          ) : null}
          {reference.availability === "truncated" ? (
            <p className={styles.warning}>后端按证据上限保留了截断内容。</p>
          ) : null}
        </>
      ) : availability === "available" ? (
        <p className={styles.hint}>
          旧记录没有类型化引用；不会按 artifact 顺序猜测模型响应。
        </p>
      ) : null}
    </div>
  );
}
