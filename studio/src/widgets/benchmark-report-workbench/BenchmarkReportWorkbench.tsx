import { useEffect, useMemo, useState } from "react";
import type { BenchmarkExperimentResource } from "@/entities/benchmark-experiment";
import type {
  BenchmarkArtifactInventoryPage,
  BenchmarkEvidenceSelection,
} from "@/entities/benchmark-report";
import {
  BenchmarkEvidenceViewer,
  BenchmarkExportDrawer,
  BenchmarkExperimentResults,
  BenchmarkEvaluationTree,
  BenchmarkReportFactsInspector,
  BenchmarkReportHeader,
  BenchmarkReportTaskRunRail,
  type BenchmarkEvaluationProjection,
  type BenchmarkExperimentResultsProjection,
  type BenchmarkReportComponentState,
  type BenchmarkReportRunItem,
  type BenchmarkReportSelection,
  type BenchmarkRunDetailProjection,
  useBenchmarkEvidenceViewer,
  useBenchmarkExport,
  type BenchmarkExportRefresh,
} from "@/features/benchmark-reporting";

type BenchmarkReportWorkbenchProps = {
  experiment: BenchmarkExperimentResource;
  experimentResults: BenchmarkExperimentResultsProjection | null;
  inventory: BenchmarkArtifactInventoryPage | null;
  runItems: BenchmarkReportRunItem[];
  selection: BenchmarkReportSelection | null;
  runDetail: BenchmarkRunDetailProjection | null;
  evaluation: BenchmarkEvaluationProjection | null;
  states: {
    publication: BenchmarkReportComponentState;
    aggregate: BenchmarkReportComponentState;
    taskRuns: BenchmarkReportComponentState;
    inventory: BenchmarkReportComponentState;
    runReport: BenchmarkReportComponentState;
    evaluation: BenchmarkReportComponentState;
    replay: BenchmarkReportComponentState;
  };
  refreshing: boolean;
  onRefreshExportMetadata: BenchmarkExportRefresh;
  onBackToMonitor: () => void;
  onRefresh: () => void;
  onRetryTaskRuns: () => void;
  onRetryPublication: () => void;
  onRetryRunReport: () => void;
  onRetryEvaluation: () => void;
  onSelectTaskRun: (taskRunId: string) => void;
  onOpenReplay: (replayId: string) => void;
};

/** Compose the report-specific rail, Evaluation, and facts workbench. */
export function BenchmarkReportWorkbench({
  experiment,
  experimentResults,
  inventory,
  runItems,
  selection,
  runDetail,
  evaluation,
  states,
  refreshing,
  onRefreshExportMetadata,
  onBackToMonitor,
  onRefresh,
  onRetryTaskRuns,
  onRetryPublication,
  onRetryRunReport,
  onRetryEvaluation,
  onSelectTaskRun,
  onOpenReplay,
}: BenchmarkReportWorkbenchProps) {
  const [exportOpen, setExportOpen] = useState(false);
  const [evidenceSelection, setEvidenceSelection] =
    useState<BenchmarkEvidenceSelection | null>(null);
  const evidenceScope = useMemo(
    () =>
      selection?.selectedTaskRunId
        ? {
            experimentId: experiment.experimentId,
            taskRunId: selection.selectedTaskRunId,
          }
        : null,
    [experiment.experimentId, selection?.selectedTaskRunId],
  );
  const evidenceViewer = useBenchmarkEvidenceViewer(
    evidenceSelection,
    evidenceScope,
    inventory,
  );
  const taskRunIds = useMemo(
    () => runItems.flatMap((item) => (
      item.taskRunId ? [item.taskRunId] : []
    )),
    [runItems],
  );
  const exportController = useBenchmarkExport(
    experiment.experimentId,
    inventory,
    taskRunIds,
    onRefreshExportMetadata,
  );
  const selectedEvidenceOrigin =
    selection?.selected?.taskRun?.result?.evidenceOrigin ?? null;

  useEffect(() => {
    setEvidenceSelection(null);
  }, [experiment.experimentId, selection?.selectedTaskRunId]);

  useEffect(() => {
    exportController.closeManifest();
  }, [exportController.closeManifest, selection?.selectedTaskRunId]);

  /** Close the drawer and release every short-lived Export request. */
  const closeExport = () => {
    exportController.reset();
    setExportOpen(false);
  };

  const publicationAvailable = states.publication.kind === "available";
  return (
    <div className="relative flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <BenchmarkReportHeader
        experiment={experiment}
        publicationState={states.publication}
        refreshing={refreshing}
        exportDisabled={states.inventory.kind !== "available"}
        onBackToMonitor={onBackToMonitor}
        onRefresh={onRefresh}
        onOpenExport={() => setExportOpen(true)}
      />
      {!publicationAvailable ? (
        <ReportStateBanner
          state={states.publication}
          onRetry={onRetryPublication}
        />
      ) : null}
      {states.inventory.kind !== "available"
        && states.inventory.kind !== "idle"
        && states.inventory.kind !== "loading" ? (
          <ReportStateBanner
            label="Artifact inventory"
            state={states.inventory}
            onRetry={onRefresh}
          />
        ) : null}
      <BenchmarkExperimentResults
        results={experimentResults}
        state={states.aggregate}
        onRetry={onRetryPublication}
      />
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-auto xl:grid-cols-[minmax(13rem,0.75fr)_minmax(22rem,2fr)_minmax(17rem,1fr)]">
        <BenchmarkReportTaskRunRail
          items={runItems}
          selection={selection}
          state={states.taskRuns}
          onSelect={onSelectTaskRun}
          onRetry={onRetryTaskRuns}
        />
        <BenchmarkEvaluationTree
          key={runDetail?.report.coreTaskRunId ?? "no-evaluation"}
          projection={evaluation}
          state={states.evaluation}
          onRetry={onRetryEvaluation}
          onOpenEvidence={setEvidenceSelection}
        />
        <BenchmarkReportFactsInspector
          experiment={experiment}
          selected={selection?.selected ?? null}
          detail={runDetail}
          state={states.runReport}
          replayState={states.replay}
          onRetry={onRetryRunReport}
          onOpenReplay={onOpenReplay}
        />
      </div>
      {evidenceSelection ? (
        <BenchmarkEvidenceViewer
          selection={evidenceSelection}
          state={evidenceViewer.state}
          evidenceOrigin={selectedEvidenceOrigin}
          onClose={() => setEvidenceSelection(null)}
          onRetry={evidenceViewer.retry}
        />
      ) : null}
      {exportOpen ? (
        <BenchmarkExportDrawer
          projection={exportController.projection}
          projectionError={exportController.projectionError}
          prepareStates={exportController.prepareStates}
          manifestState={exportController.manifestState}
          evidenceOrigin={selectedEvidenceOrigin}
          onPrepare={(material) => {
            void exportController.prepare(material);
          }}
          onHandOff={exportController.markHandedOff}
          onReviewManifest={(material) => {
            void exportController.loadManifest(material);
          }}
          onCloseManifest={exportController.closeManifest}
          onClose={closeExport}
        />
      ) : null}
    </div>
  );
}

/** Render one safe scoped state while retaining verified sibling regions. */
function ReportStateBanner({
  label = "Experiment report",
  state,
  onRetry,
}: {
  label?: string;
  state: BenchmarkReportComponentState;
  onRetry: () => void;
}) {
  return (
    <div
      role="status"
      data-state={state.kind}
      className="flex items-center justify-between gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-[10px] text-amber-200"
    >
      <span>
        {label}: {state.message}
      </span>
      {state.retryable ? (
        <button type="button" onClick={onRetry} className="underline">
          Retry
        </button>
      ) : null}
    </div>
  );
}
