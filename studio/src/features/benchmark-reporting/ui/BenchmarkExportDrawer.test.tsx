import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  parseBenchmarkArtifactInventoryPage,
  reportExperimentId,
  reportTaskRunId,
  type BenchmarkArtifactInventoryItem,
  type BenchmarkPublicationManifestSummary,
} from "@/entities/benchmark-report";
import {
  projectBenchmarkExportMaterials,
} from "../model/benchmarkExportMaterials";
import type {
  BenchmarkExportPrepareState,
} from "../model/useBenchmarkExport";
import { BenchmarkExportDrawer } from "./BenchmarkExportDrawer";

const HASH = `sha256:${"a".repeat(64)}`;
const BUNDLE_ID = `artifact-${"2".padStart(32, "0")}`;

afterEach(cleanup);

/** Build one strict inventory item with an exact scoped content capability. */
function item(
  ordinal: number,
  kind: string,
  taskRunId: string | null,
  availability = "available",
  contentType = "application/json",
): BenchmarkArtifactInventoryItem {
  const artifactId = ordinal === 2
    ? BUNDLE_ID
    : `artifact-${ordinal.toString(16).padStart(32, "0")}`;
  const scope = taskRunId === null
    ? `/studio/benchmark-experiments/${reportExperimentId}/artifacts/`
    : `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
      + `${taskRunId}/artifacts/`;
  const readable = ["available", "redacted", "truncated"].includes(
    availability,
  );
  return {
    schemaVersion: 1,
    descriptor: {
      schemaVersion: 1,
      artifactId,
      experimentId: reportExperimentId,
      taskRunId,
      kind,
      availability: availability as "available",
      contentType: readable ? contentType : "",
      size: readable ? ordinal * 10 : 0,
      sha256: readable ? HASH : null,
      provenance: "fixture",
      causalIdentity: `${kind}-${ordinal}.json`,
      hidden: false,
    },
    links: { content: readable ? `${scope}${artifactId}` : null },
  };
}

/** Build a complete Export projection with more than one evidence page. */
function projection() {
  const items = [
    item(1, "experiment_report", null),
    item(2, "experiment_bundle", null, "available", "application/zip"),
    item(3, "studio_publication_manifest", null),
    item(4, "task_report", reportTaskRunId),
    item(5, "task_trajectory", reportTaskRunId, "available", "application/x-ndjson"),
    ...Array.from({ length: 11 }, (_, index) =>
      item(10 + index, "model_response", reportTaskRunId)
    ),
    item(30, "screenshot", reportTaskRunId, "missing"),
    item(31, "ui_xml", reportTaskRunId, "corrupt"),
  ];
  return projectBenchmarkExportMaterials(
    reportExperimentId,
    parseBenchmarkArtifactInventoryPage({
      schemaVersion: 1,
      experimentId: reportExperimentId,
      items,
      hiddenCount: 3,
      nextCursor: null,
    }),
  );
}

/** Render the drawer with isolated transport and manifest states. */
function renderDrawer(
  states: ReadonlyMap<string, BenchmarkExportPrepareState> = new Map(),
  manifestState: Parameters<typeof BenchmarkExportDrawer>[0]["manifestState"] = {
    kind: "idle",
  },
) {
  const value = projection();
  const handlers = {
    prepare: vi.fn(),
    handOff: vi.fn(),
    review: vi.fn(),
    closeManifest: vi.fn(),
    close: vi.fn(),
  };
  render(
    <BenchmarkExportDrawer
      projection={value}
      projectionError={null}
      prepareStates={states}
      manifestState={manifestState}
      evidenceOrigin={{
        schemaVersion: 1,
        acquisition: "contract_fixture",
        environment: "fake_device",
        deviceProfileId: "acceptance-fake",
        deviceChecks: [],
        realDeviceEvidence: false,
      }}
      onPrepare={handlers.prepare}
      onHandOff={handlers.handOff}
      onReviewManifest={handlers.review}
      onCloseManifest={handlers.closeManifest}
      onClose={handlers.close}
    />,
  );
  return { value, handlers };
}

describe("BenchmarkExportDrawer", () => {
  it("groups exact scopes, paginates evidence, and keeps partial failures local", () => {
    const value = projection();
    const failed = value.experimentBundle!;
    const states = new Map<string, BenchmarkExportPrepareState>([
      [
        failed.key,
        {
          kind: "failed",
          failure: "header-conflict",
          availability: "available",
          retryable: true,
        },
      ],
    ]);
    const { handlers } = renderDrawer(states);
    const dialog = screen.getByRole("dialog", { name: "Benchmark export" });
    expect(document.activeElement).toBe(dialog);
    expect(
      within(screen.getByLabelText("TaskRun materials")).getByText(
        reportTaskRunId,
      ),
    ).not.toBeNull();
    expect(screen.queryByText(/raw backend exception/i)).toBeNull();
    expect(screen.getByText(/Response headers conflict/)).not.toBeNull();
    expect(screen.getByText(/Hidden artifact descriptors: 3/)).not.toBeNull();
    expect(screen.getByText("Supporting fake-device fixture")).not.toBeNull();
    expect(screen.getByText("1 / 2")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Next evidence" }));
    expect(screen.getByText("2 / 2")).not.toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Prepare export" })[0]!);
    expect(handlers.prepare).toHaveBeenCalledOnce();
  });

  it("renders declared manifest facts without member capabilities", () => {
    const summary: BenchmarkPublicationManifestSummary = {
      experimentId: reportExperimentId,
      taskRunId: reportTaskRunId,
      memberCount: 1,
      declaredBytes: 128,
      members: [
        {
          reference: "runs/result.json",
          kind: "task_result",
          contentType: "application/json",
          size: 128,
          sha256: HASH,
          scope: {
            experimentId: reportExperimentId,
            taskRunId: reportTaskRunId,
          },
          availability: "available",
          exclusionReason: "",
        },
      ],
      excludedEvidence: [
        {
          kind: "prompt",
          availability: "hidden",
          reason: "hidden_by_default_policy",
        },
      ],
    };
    renderDrawer(new Map(), { kind: "ready", summary });
    expect(
      screen.getByLabelText("Publication manifest review").textContent,
    ).toContain(BUNDLE_ID);
    expect(
      screen.getByRole("table", { name: "Publication manifest members" }),
    ).not.toBeNull();
    expect(screen.getByText("runs/result.json")).not.toBeNull();
    expect(screen.getByText(/not standalone inventory capabilities/))
      .not.toBeNull();
    expect(screen.getByText(/hidden_by_default_policy/)).not.toBeNull();
    expect(
      screen.queryByRole("link", { name: /runs\/result\.json/ }),
    ).toBeNull();
  });

  it("shows a browser handoff only after preparation and makes no completion claim", () => {
    const value = projection();
    const report = value.experimentReport!;
    const states = new Map<string, BenchmarkExportPrepareState>([
      [
        report.key,
        {
          kind: "ready-for-handoff",
          item: report.item,
          head: {
            contentType: "application/json",
            contentLength: report.item.descriptor.size,
            filename: `${reportExperimentId}.report.json`,
          },
        },
      ],
    ]);
    const { handlers } = renderDrawer(states);
    const link = screen.getByRole("link", { name: "Hand off to browser" });
    expect(link.getAttribute("href")).toContain(report.item.links.content!);
    fireEvent.click(link);
    expect(handlers.handOff).toHaveBeenCalledWith(report);
    expect(screen.queryByText(/export complete/i)).toBeNull();
    expect(screen.queryByText(/downloaded/i)).toBeNull();
  });

  it("closes from Escape without persisting drawer state", () => {
    const { handlers } = renderDrawer();
    fireEvent.keyDown(
      screen.getByRole("dialog", { name: "Benchmark export" }),
      { key: "Escape" },
    );
    expect(handlers.close).toHaveBeenCalledOnce();
  });
});
