import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  parseBenchmarkArtifactInventoryPage,
  parseBenchmarkRunReport,
} from "@/entities/benchmark-report";
import { BenchmarkEvidenceViewer } from "./BenchmarkEvidenceViewer";

afterEach(cleanup);

/** Build safe strict Viewer props without loading a body. */
function fixture() {
  const evidence = parseBenchmarkRunReport(
    benchmarkRunReportFixture(),
  ).evaluation!.children[0]!.evaluatorResult!.evidence[0]!;
  const item = parseBenchmarkArtifactInventoryPage(
    benchmarkReportInventoryFixture(),
  ).items[0]!;
  return {
    selection: {
      leafPath: "root/leaf",
      evidenceIndex: 0,
      evidence: { ...evidence, artifactRef: item.descriptor.causalIdentity },
    },
    item,
  };
}

describe("BenchmarkEvidenceViewer", () => {
  it("renders script-looking JSON as escaped text and preserves availability", () => {
    const value = fixture();
    value.item.descriptor.availability = "redacted";
    render(
      <BenchmarkEvidenceViewer
        selection={value.selection}
        evidenceOrigin={{
          schemaVersion: 1,
          acquisition: "replay_projection",
          environment: "real_android",
          deviceProfileId: "pixel-safe",
          deviceChecks: [],
          realDeviceEvidence: false,
        }}
        state={{
          kind: "ready-text",
          item: value.item,
          hiddenCount: 0,
          language: "json",
          text: '{"value":"<script>SECRET</script>"}',
        }}
        onClose={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText("redacted")).not.toBeNull();
    expect(
      screen.getByText("Historical projection of a real-Android source"),
    ).not.toBeNull();
    expect(screen.getByText(/<script>SECRET<\/script>/)).not.toBeNull();
    expect(document.querySelector("script")).toBeNull();
  });

  it("uses truthful download-only wording and the exact capability", () => {
    const value = fixture();
    render(
      <BenchmarkEvidenceViewer
        selection={value.selection}
        state={{
          kind: "download-only",
          item: value.item,
          hiddenCount: 0,
          url: value.item.links.content!,
          contentType: "application/zip",
        }}
        onClose={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText(/does not claim download or verification completion/))
      .not.toBeNull();
    expect(
      screen.getByRole("link", { name: "Hand off evidence download" })
        .getAttribute("href"),
    ).toBe(value.item.links.content);
  });

  it("keeps hidden count aggregate and never exposes a raw backend error", () => {
    const value = fixture();
    let retried = false;
    render(
      <BenchmarkEvidenceViewer
        selection={value.selection}
        state={{
          kind: "request-failed",
          item: value.item,
          hiddenCount: 3,
          retryable: true,
        }}
        onClose={() => undefined}
        onRetry={() => {
          retried = true;
        }}
      />,
    );
    expect(screen.getByText(/none is attributed to this leaf/)).not.toBeNull();
    expect(screen.queryByText(/SECRET RAW BACKEND DETAIL/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry evidence" }));
    expect(retried).toBe(true);
  });

  it("exposes an accessible Close action independently of Report state", () => {
    const value = fixture();
    let closed = false;
    render(
      <BenchmarkEvidenceViewer
        selection={value.selection}
        state={{ kind: "no-reference", hiddenCount: 0 }}
        onClose={() => {
          closed = true;
        }}
        onRetry={() => undefined}
      />,
    );
    expect(
      screen.getByRole("dialog", { name: "Benchmark evidence viewer" }),
    ).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(closed).toBe(true);
  });
});
