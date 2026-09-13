import styles from "./workbenchChrome.module.css";

/** Resolve one compact title without treating mutable metadata as execution identity. */
export function resolveAgentTitle(name: string | null | undefined, agentId: string): string {
  const trimmed = name?.trim();
  if (trimmed) return trimmed;
  const suffix = agentId.length > 18 ? `${agentId.slice(0, 18)}…` : agentId;
  return suffix ? `Agent ${suffix}` : "Agent 名称不可用";
}

/** Render the compact workbench title whose only visible fact is the Agent name. */
export function WorkbenchAgentTitle({ name }: { name: string }) {
  return (
    <header className={styles.title} aria-label="Agent name">
      <h1>{name}</h1>
    </header>
  );
}

/** Stack mode-specific playback and task controls below the shared panes. */
export function RunWorkspaceDock({
  upper,
  lower,
}: {
  upper?: React.ReactNode;
  lower: React.ReactNode;
}) {
  return (
    <footer className={styles.dock} aria-label="Run workspace controls">
      {upper ? <div className={styles.upper}>{upper}</div> : null}
      <div className={styles.lower}>{lower}</div>
    </footer>
  );
}

/** Explain why a Replay stays inspectable but cannot launch an ordinary Run. */
export function ReadOnlyRunReason({ reason }: { reason: string }) {
  return (
    <div className={styles.readOnlyReason} role="status">
      <strong>只读 Replay</strong>
      <span>{reason}</span>
    </div>
  );
}
