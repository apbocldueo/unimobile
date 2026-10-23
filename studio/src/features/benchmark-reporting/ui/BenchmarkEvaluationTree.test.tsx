import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  benchmarkRunReportFixture,
  parseBenchmarkRunReport,
  type BenchmarkEvaluationNode,
} from "@/entities/benchmark-report";
import {
  benchmarkReportState,
  projectBenchmarkEvaluation,
} from "@/features/benchmark-reporting";
import { BenchmarkEvaluationTree } from "./BenchmarkEvaluationTree";

/** Parse the publisher-shaped Evaluation Tree used by UI contract tests. */
function evaluationRoot(): BenchmarkEvaluationNode {
  return parseBenchmarkRunReport(benchmarkRunReportFixture()).evaluation!;
}

afterEach(cleanup);

describe("BenchmarkEvaluationTree", () => {
  it("renders tri-state facts, safe redaction, and collapsed descendants", () => {
    const root = evaluationRoot();
    root.children.push({
      ...structuredClone(root.children[0]!),
      path: "root/not-passed",
      name: "not-passed",
      status: "failure",
      isPass: false,
      shortCircuited: true,
    });
    render(
      <BenchmarkEvaluationTree
        projection={projectBenchmarkEvaluation(root)}
        state={benchmarkReportState("available", "available")}
        onRetry={() => undefined}
      />,
    );

    expect(screen.getByText(/pass undetermined/)).not.toBeNull();
    expect(screen.getAllByText(/pass passed/).length).toBeGreaterThan(0);
    expect(screen.getByText(/pass not passed/)).not.toBeNull();
    expect(screen.getAllByText(/safely redacted/).length).toBeGreaterThan(0);
    expect(screen.getByText("short-circuited")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByText("leaf")).toBeNull();
    expect(screen.queryByText("not-passed")).toBeNull();
  });

  it("mounts only expanded branches in a large legal tree", () => {
    const root = evaluationRoot();
    root.children = Array.from({ length: 40 }, (_, index) => ({
      ...structuredClone(root.children[0]!),
      path: `root/leaf-${index}`,
      name: `leaf-${index}`,
      status: "success",
      isPass: true,
      children: [],
    }));
    render(
      <BenchmarkEvaluationTree
        projection={projectBenchmarkEvaluation(root)}
        state={benchmarkReportState("available", "available")}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText("leaf-39")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByText("leaf-39")).toBeNull();
    expect(document.querySelectorAll("[role=treeitem]")).toHaveLength(1);
  });

  it("keeps null Evaluation as an explicit independently retryable state", () => {
    let retried = false;
    render(
      <BenchmarkEvaluationTree
        projection={null}
        state={benchmarkReportState(
          "unavailable",
          "This TaskRun report has no Evaluation Tree.",
          true,
        )}
        onRetry={() => {
          retried = true;
        }}
      />,
    );
    expect(screen.getByText(/no Evaluation Tree/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry Evaluation" }));
    expect(retried).toBe(true);
  });

  it("emits a typed open intent only for a non-empty causal reference", () => {
    const root = evaluationRoot();
    root.children[0]!.evaluatorResult!.evidence[0]!.artifactRef =
      "runs/evidence.json";
    let selected = "";
    render(
      <BenchmarkEvaluationTree
        projection={projectBenchmarkEvaluation(root)}
        state={benchmarkReportState("available", "available")}
        onRetry={() => undefined}
        onOpenEvidence={(intent) => {
          selected = `${intent.leafPath}:${intent.evidenceIndex}:`
            + intent.evidence.artifactRef;
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open evidence" }));
    expect(selected).toBe("root/leaf:0:runs/evidence.json");
  });
});
