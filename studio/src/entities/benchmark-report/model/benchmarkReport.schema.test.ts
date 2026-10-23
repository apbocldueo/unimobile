import { describe, expect, it } from "vitest";
import {
  benchmarkExperimentReportFixture,
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  multiAgentExperimentReportFixture,
  reportCoreTaskRunId,
  reportExperimentId,
  reportTaskRunId,
} from "../testing/benchmarkReport.fixtures";
import {
  parseBenchmarkArtifactInventoryPage,
  parseBenchmarkExperimentReport,
  parseBenchmarkRunReport,
  resolveBenchmarkRunReportArtifact,
} from "./benchmarkReport.schema";

describe("Benchmark reporting contracts", () => {
  it("parses authoritative single and synthetic multi-Agent reports", () => {
    const single = parseBenchmarkExperimentReport(
      benchmarkExperimentReportFixture(),
      reportExperimentId,
    );
    const multi = parseBenchmarkExperimentReport(
      multiAgentExperimentReportFixture(),
      reportExperimentId,
    );
    expect(single.agentMetrics[0]?.successRateMicro).toBe(1);
    expect(multi.agentMetrics).toHaveLength(2);
    expect(multi.comparisons[0]?.matchedCount).toBe(1);
  });

  it("rejects unknown schemas, fields, denominator, rate and interval drift", () => {
    expect(() =>
      parseBenchmarkExperimentReport({
        ...benchmarkExperimentReportFixture(),
        schema_version: "2.0",
      }),
    ).toThrow(/unsupported/);
    expect(() =>
      parseBenchmarkExperimentReport({
        ...benchmarkExperimentReportFixture(),
        surprise: true,
      }),
    ).toThrow(/not supported/);
    const invalidEligible = structuredClone(benchmarkExperimentReportFixture());
    invalidEligible.agent_metrics[0]!.eligible_count = 2;
    expect(() => parseBenchmarkExperimentReport(invalidEligible)).toThrow(
      /PASS plus FAIL/,
    );
    const invalidRate = structuredClone(benchmarkExperimentReportFixture());
    invalidRate.agent_metrics[0]!.success_rate_micro = 1.1;
    expect(() => parseBenchmarkExperimentReport(invalidRate)).toThrow(
      /zero and one/,
    );
    const invalidInterval = structuredClone(benchmarkExperimentReportFixture());
    invalidInterval.agent_metrics[0]!.wilson_interval_95 = [0.8, 0.2];
    expect(() => parseBenchmarkExperimentReport(invalidInterval)).toThrow(
      /interval_95 is invalid/,
    );
  });

  it("rejects comparison cardinality and unsupported significance claims", () => {
    const invalid = structuredClone(multiAgentExperimentReportFixture());
    invalid.comparisons[0]!.matched_count = 2;
    expect(() => parseBenchmarkExperimentReport(invalid)).toThrow(
      /pair outcomes/,
    );
    const significance = structuredClone(multiAgentExperimentReportFixture());
    significance.significance_claimed = true;
    expect(() => parseBenchmarkExperimentReport(significance)).toThrow(
      /cannot claim significance/,
    );
  });

  it("preserves Evaluation three-state decisions and enforces selected scope", () => {
    const report = parseBenchmarkRunReport(benchmarkRunReportFixture(), {
      experimentId: reportExperimentId,
      taskRunId: reportTaskRunId,
      coreTaskRunId: reportCoreTaskRunId,
      taskId: "task-1",
      agentId: "agent-1",
      repeat: 0,
    });
    expect(report.evaluation?.isPass).toBeNull();
    expect(report.evaluation?.token).toBe("<redacted>");
    expect(report.evaluation?.children[0]?.isPass).toBe(true);
    expect(() =>
      parseBenchmarkRunReport(benchmarkRunReportFixture(), {
        experimentId: reportExperimentId,
        taskRunId: reportTaskRunId,
        coreTaskRunId: reportCoreTaskRunId,
        taskId: "different-task",
        agentId: "agent-1",
        repeat: 0,
      }),
    ).toThrow(/selected TaskRun scope/);
  });

  it("accepts only exact safe token redaction or finite numeric tokens", () => {
    const numeric = structuredClone(
      benchmarkRunReportFixture(),
    ) as unknown as { evaluation: { token: unknown } };
    numeric.evaluation!.token = 0.5;
    expect(parseBenchmarkRunReport(numeric).evaluation?.token).toBe(0.5);

    const arbitrary = structuredClone(
      benchmarkRunReportFixture(),
    ) as unknown as { evaluation: { token: unknown } };
    arbitrary.evaluation!.token = "visible-token";
    expect(() => parseBenchmarkRunReport(arbitrary)).toThrow(/finite number/);

    const nonFinite = structuredClone(
      benchmarkRunReportFixture(),
    ) as unknown as { evaluation: { token: unknown } };
    nonFinite.evaluation!.token = Number.POSITIVE_INFINITY;
    expect(() => parseBenchmarkRunReport(nonFinite)).toThrow(/finite number/);
  });

  it("rejects Evaluation Trees beyond depth and total-node limits", () => {
    const report = structuredClone(
      benchmarkRunReportFixture(),
    ) as unknown as {
      evaluation: Record<string, unknown> & { children: unknown[] };
    };
    let node: { children: unknown[] } = report.evaluation;
    node.children = [];
    for (let depth = 0; depth < 32; depth += 1) {
      const child: Record<string, unknown> & { children: unknown[] } = {
        ...structuredClone(report.evaluation!),
        path: `root/${depth}`,
        evaluator_result: null,
        children: [],
      };
      node.children = [child];
      node = child;
    }
    expect(() => parseBenchmarkRunReport(report)).toThrow(
      /Evaluation Tree limits/,
    );

    const oversized = structuredClone(
      benchmarkRunReportFixture(),
    ) as unknown as {
      evaluation: Record<string, unknown> & { children: unknown[] };
    };
    const leaf = structuredClone(
      oversized.evaluation.children[0],
    ) as Record<string, unknown> & { children: unknown[] };
    leaf.children = [];
    oversized.evaluation!.children = Array.from({ length: 50 }, (_, branch) => ({
      ...structuredClone(leaf),
      path: `root/branch-${branch}`,
      children: Array.from({ length: 40 }, (_, child) => ({
        ...structuredClone(leaf),
        path: `root/branch-${branch}/leaf-${child}`,
      })),
    }));
    expect(() => parseBenchmarkRunReport(oversized)).toThrow(
      /Evaluation Tree limits/,
    );
  });

  it("parses inventory and resolves only exact same-scope causal evidence", () => {
    const inventory = parseBenchmarkArtifactInventoryPage(
      benchmarkReportInventoryFixture(),
    );
    const report = parseBenchmarkExperimentReport(
      benchmarkExperimentReportFixture(),
    );
    expect(
      resolveBenchmarkRunReportArtifact(
        {
          experimentId: reportExperimentId,
          taskRunId: reportTaskRunId,
          coreTaskRunId: reportCoreTaskRunId,
        },
        report.runSummaries[0]!,
        inventory,
      ).links.content,
    ).toContain(reportTaskRunId);

    const wrongScope = structuredClone(benchmarkReportInventoryFixture());
    wrongScope.items[0]!.descriptor.taskRunId = `task-run-${"f".repeat(32)}`;
    expect(() =>
      parseBenchmarkArtifactInventoryPage(wrongScope),
    ).toThrow(/expected artifact scope/);

    const missingReference = structuredClone(benchmarkReportInventoryFixture());
    missingReference.items[0]!.descriptor.causalIdentity = "runs/other/report.json";
    expect(() =>
      resolveBenchmarkRunReportArtifact(
        {
          experimentId: reportExperimentId,
          taskRunId: reportTaskRunId,
          coreTaskRunId: reportCoreTaskRunId,
        },
        report.runSummaries[0]!,
        parseBenchmarkArtifactInventoryPage(missingReference),
      ),
    ).toThrow(/unavailable or inconsistent/);

    const ambiguous = structuredClone(benchmarkReportInventoryFixture());
    const duplicate = structuredClone(ambiguous.items[0]!);
    duplicate.descriptor.artifactId = `artifact-${"d".repeat(32)}`;
    duplicate.links.content =
      `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
      + `${reportTaskRunId}/artifacts/${duplicate.descriptor.artifactId}`;
    ambiguous.items.push(duplicate);
    expect(() =>
      resolveBenchmarkRunReportArtifact(
        {
          experimentId: reportExperimentId,
          taskRunId: reportTaskRunId,
          coreTaskRunId: reportCoreTaskRunId,
        },
        report.runSummaries[0]!,
        parseBenchmarkArtifactInventoryPage(ambiguous),
      ),
    ).toThrow(/ambiguous/);

    expect(() =>
      resolveBenchmarkRunReportArtifact(
        {
          experimentId: reportExperimentId,
          taskRunId: reportTaskRunId,
          coreTaskRunId: "8".repeat(32),
        },
        report.runSummaries[0]!,
        inventory,
      ),
    ).toThrow(/Experiment scope/);
  });

  it("fails closed on hidden, unknown and malformed readable artifacts", () => {
    const unknown = structuredClone(benchmarkReportInventoryFixture());
    unknown.items[0]!.descriptor.availability = "future";
    expect(() => parseBenchmarkArtifactInventoryPage(unknown)).toThrow(
      /unsupported artifact availability/,
    );
    const missingHash = structuredClone(
      benchmarkReportInventoryFixture(),
    ) as unknown as {
      items: Array<{ descriptor: { sha256: string | null } }>;
    };
    missingHash.items[0]!.descriptor.sha256 = null;
    expect(() => parseBenchmarkArtifactInventoryPage(missingHash)).toThrow(
      /requires content type and hash/,
    );
    const hidden = structuredClone(
      benchmarkReportInventoryFixture(),
    ) as unknown as {
      items: Array<{
        descriptor: {
          availability: string;
          hidden: boolean;
          contentType: string;
          size: number;
          sha256: string | null;
        };
        links: { content: string | null };
      }>;
    };
    hidden.items[0]!.descriptor.availability = "hidden";
    hidden.items[0]!.descriptor.hidden = true;
    hidden.items[0]!.descriptor.contentType = "";
    hidden.items[0]!.descriptor.size = 0;
    hidden.items[0]!.descriptor.sha256 = null;
    hidden.items[0]!.links.content = null;
    expect(() => parseBenchmarkArtifactInventoryPage(hidden)).toThrow(
      /hidden or cross-Experiment/,
    );
  });
});
