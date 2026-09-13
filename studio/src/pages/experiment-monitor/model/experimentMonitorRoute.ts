export type ExperimentMonitorRoute =
  | { mode: "monitor"; experimentId: string }
  | { mode: "invalid"; reason: string };

const EXPERIMENT_ID = /^experiment-[a-f0-9]{32}$/;

/** Parse one stable Experiment Monitor route parameter without coercion. */
export function parseExperimentMonitorRoute(
  experimentId: string | undefined,
): ExperimentMonitorRoute {
  if (!experimentId) {
    return { mode: "invalid", reason: "路由缺少 experimentId。" };
  }
  if (!EXPERIMENT_ID.test(experimentId)) {
    return {
      mode: "invalid",
      reason: "experimentId 不符合版本化 Studio identity contract。",
    };
  }
  return { mode: "monitor", experimentId };
}
