export const reportExperimentId = `experiment-${"a".repeat(32)}`;
export const reportTaskRunId = `task-run-${"b".repeat(32)}`;
export const reportCoreTaskRunId = "9".repeat(32);
export const reportArtifactId = `artifact-${"c".repeat(32)}`;
export const reportHash = `sha256:${"d".repeat(64)}`;

/** Build one authoritative single-Agent Core Experiment report. */
export function benchmarkExperimentReportFixture() {
  return {
    schema_version: "1.0",
    kind: "benchmark_experiment_report",
    experiment_id: reportExperimentId,
    benchmark_plan_identity: reportHash,
    experiment_protocol_identity: reportHash,
    counts: { pass: 1, fail: 0, invalid: 0, skipped: 0 },
    agent_metrics: [
      {
        agent_id: "agent-1",
        counts: { pass: 1, fail: 0, invalid: 0, skipped: 0 },
        eligible_count: 1,
        success_rate_micro: 1,
        success_rate_macro: 1,
        duration_mean_ms: 12,
        duration_median_ms: 12,
        duration_sample_variance: null,
        wilson_interval_95: [0.2, 1],
        usage_available_runs: 1,
      },
    ],
    comparisons: [],
    run_summaries: [
      {
        task_run_id: reportCoreTaskRunId,
        task_id: "task-1",
        agent_id: "agent-1",
        repeat: 0,
        outcome: "pass",
        report_ref: `runs/${reportCoreTaskRunId}/run-report.json`,
        trajectory_ref: `runs/${reportCoreTaskRunId}/trajectory.jsonl`,
      },
    ],
    fairness_warnings: [],
    significance_claimed: false,
  };
}

/** Build one synthetic two-Agent report for parser-only contract evidence. */
export function multiAgentExperimentReportFixture() {
  const secondCoreTaskRunId = "e".repeat(32);
  return {
    ...benchmarkExperimentReportFixture(),
    counts: { pass: 1, fail: 1, invalid: 0, skipped: 0 },
    agent_metrics: [
      benchmarkExperimentReportFixture().agent_metrics[0],
      {
        agent_id: "agent-2",
        counts: { pass: 0, fail: 1, invalid: 0, skipped: 0 },
        eligible_count: 1,
        success_rate_micro: 0,
        success_rate_macro: 0,
        duration_mean_ms: 14,
        duration_median_ms: 14,
        duration_sample_variance: null,
        wilson_interval_95: [0, 0.8],
        usage_available_runs: 0,
      },
    ],
    comparisons: [
      {
        left_agent_id: "agent-1",
        right_agent_id: "agent-2",
        paired: true,
        matched_count: 1,
        unmatched_eligible_count: 0,
        left_wins: 1,
        right_wins: 0,
        ties: 0,
        significance_claimed: false,
      },
    ],
    run_summaries: [
      benchmarkExperimentReportFixture().run_summaries[0],
      {
        task_run_id: secondCoreTaskRunId,
        task_id: "task-1",
        agent_id: "agent-2",
        repeat: 0,
        outcome: "fail",
        report_ref: `runs/${secondCoreTaskRunId}/run-report.json`,
        trajectory_ref: `runs/${secondCoreTaskRunId}/trajectory.jsonl`,
      },
    ],
  };
}

/** Build synthetic aggregate edge states for comparison presentation tests. */
export function comparisonMetricsExperimentReportFixture() {
  const failedCoreTaskRunId = "e".repeat(32);
  const invalidCoreTaskRunId = "7".repeat(32);
  const skippedCoreTaskRunId = "8".repeat(32);
  return {
    ...benchmarkExperimentReportFixture(),
    counts: { pass: 1, fail: 1, invalid: 1, skipped: 1 },
    agent_metrics: [
      {
        ...benchmarkExperimentReportFixture().agent_metrics[0],
        duration_mean_ms: 0,
        duration_median_ms: 0,
        duration_sample_variance: 0,
      },
      {
        agent_id: "agent-2",
        counts: { pass: 0, fail: 1, invalid: 0, skipped: 0 },
        eligible_count: 1,
        success_rate_micro: 0,
        success_rate_macro: 0,
        duration_mean_ms: 14,
        duration_median_ms: 14,
        duration_sample_variance: null,
        wilson_interval_95: [0, 0.8],
        usage_available_runs: 0,
      },
      {
        agent_id: "agent-3",
        counts: { pass: 0, fail: 0, invalid: 1, skipped: 1 },
        eligible_count: 0,
        success_rate_micro: null,
        success_rate_macro: null,
        duration_mean_ms: null,
        duration_median_ms: null,
        duration_sample_variance: null,
        wilson_interval_95: null,
        usage_available_runs: 0,
      },
    ],
    comparisons: [
      {
        left_agent_id: "agent-1",
        right_agent_id: "agent-2",
        paired: true,
        matched_count: 1,
        unmatched_eligible_count: 2,
        left_wins: 1,
        right_wins: 0,
        ties: 0,
        significance_claimed: false,
      },
      {
        left_agent_id: "agent-1",
        right_agent_id: "agent-3",
        paired: false,
        matched_count: 0,
        unmatched_eligible_count: 1,
        left_wins: 0,
        right_wins: 0,
        ties: 0,
        significance_claimed: false,
      },
    ],
    run_summaries: [
      benchmarkExperimentReportFixture().run_summaries[0],
      {
        task_run_id: failedCoreTaskRunId,
        task_id: "task-1",
        agent_id: "agent-2",
        repeat: 0,
        outcome: "fail",
        report_ref: `runs/${failedCoreTaskRunId}/run-report.json`,
        trajectory_ref: `runs/${failedCoreTaskRunId}/trajectory.jsonl`,
      },
      {
        task_run_id: invalidCoreTaskRunId,
        task_id: "task-2",
        agent_id: "agent-3",
        repeat: 0,
        outcome: "invalid",
        report_ref: `runs/${invalidCoreTaskRunId}/run-report.json`,
        trajectory_ref: `runs/${invalidCoreTaskRunId}/trajectory.jsonl`,
      },
      {
        task_run_id: skippedCoreTaskRunId,
        task_id: "task-3",
        agent_id: "agent-3",
        repeat: 0,
        outcome: "skipped",
        report_ref: `runs/${skippedCoreTaskRunId}/run-report.json`,
        trajectory_ref: `runs/${skippedCoreTaskRunId}/trajectory.jsonl`,
      },
    ],
    fairness_warnings: [
      "benchmark.protocol.unpaired_materialization",
      "benchmark.protocol.shared_device_state_across_agents",
      "benchmark.protocol.synthetic_unknown_warning",
    ],
  };
}

/** Build one Core TaskRun report with a typed three-state Evaluation Tree. */
export function benchmarkRunReportFixture() {
  return {
    schema_version: "1.0",
    kind: "benchmark_run_report",
    task_run_id: reportCoreTaskRunId,
    experiment_id: reportExperimentId,
    task_id: "task-1",
    agent_id: "agent-1",
    repeat: 0,
    outcome: "pass",
    identities: {
      agent_graph: reportHash,
      benchmark_plan: reportHash,
      experiment_protocol: reportHash,
      task_instance: reportHash,
    },
    stages: [
      {
        phase: "evaluation",
        status: "success",
        duration_ms: 12,
        error_code: "",
        message: "",
        evidence: {},
        artifact_refs: [],
      },
    ],
    evaluation: {
      path: "root",
      name: "all",
      status: "success",
      is_pass: null,
      reason: "",
      token: "<redacted>",
      score: 1,
      duration_ms: 5,
      evidence: {},
      aggregation: { method: "all" },
      evaluator_result: null,
      short_circuited: false,
      children: [
        {
          path: "root/leaf",
          name: "leaf",
          status: "success",
          is_pass: true,
          reason: "matched",
          token: "<redacted>",
          score: 1,
          duration_ms: 4,
          evidence: {},
          aggregation: {},
          evaluator_result: {
            schema_version: "2.0",
            evaluator_id: "evaluator-1",
            status: "completed",
            passed: true,
            score: 1,
            reason: "matched",
            duration_ms: 4,
            usage: {
              availability: "available",
              prompt_tokens: 1,
              completion_tokens: 1,
              total_tokens: 2,
            },
            evidence: [
              {
                kind: "text.match",
                value: { found: true },
                artifact_ref: "",
                metadata: {},
              },
            ],
            metadata: {},
            error_code: "",
          },
          short_circuited: false,
          children: [],
        },
      ],
    },
    usage: { total_tokens: 2 },
    artifact_namespace: reportCoreTaskRunId,
  };
}

/** Build the inventory item that safely resolves the TaskRun report. */
export function benchmarkReportInventoryFixture() {
  return {
    schemaVersion: 1,
    experimentId: reportExperimentId,
    items: [
      {
        schemaVersion: 1,
        descriptor: {
          schemaVersion: 1,
          artifactId: reportArtifactId,
          experimentId: reportExperimentId,
          taskRunId: reportTaskRunId,
          kind: "task_report",
          availability: "available",
          contentType: "application/json",
          size: 100,
          sha256: reportHash,
          provenance: "native_benchmark",
          causalIdentity: `runs/${reportCoreTaskRunId}/run-report.json`,
          hidden: false,
        },
        links: {
          content:
            `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
            + `${reportTaskRunId}/artifacts/${reportArtifactId}`,
        },
      },
    ],
    hiddenCount: 0,
    nextCursor: null,
  };
}
