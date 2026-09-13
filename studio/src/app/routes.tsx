import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "@/app/shell/AppShell";
import { ModuleNavSwitchProvider } from "@/app/shell/ModuleNavSwitchContext";
import { ToastViewport } from "@/app/shell/ToastViewport";

import { AgentBuilderDesignPage, AgentBuilderEntryPage } from "@/pages/agent-builder";
import { AgentLibraryPage } from "@/pages/agent-library";
import { AgentRunPage } from "@/pages/agent-run";
import { BenchmarkDetailPage } from "@/pages/benchmark-detail";
import { BenchmarkAuthoringPage } from "@/pages/benchmark-authoring";
import { BenchmarkDraftEditPage } from "@/pages/benchmark-draft-edit";
import { BenchmarksPage } from "@/pages/benchmarks";
import { ExperimentCreatePage } from "@/pages/experiment-create";
import { ExperimentHistoryPage } from "@/pages/experiment-history";
import { ExperimentMonitorPage } from "@/pages/experiment-monitor";
import { ExperimentReportPage } from "@/pages/experiment-report";
import { RunHistoryPage } from "@/pages/run-history";
import { RunReplayPage } from "@/pages/run-replay";
import { NotFoundPage } from "@/pages/not-found";
import { HelpCenterPage } from "@/features/help-center/HelpCenterPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StudioHomePage } from "@/pages/studio-home";

export function AppRoutes() {
  return (
    <ModuleNavSwitchProvider>
      <>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<StudioHomePage />} />
            <Route path="agents" element={<AgentLibraryPage />} />
            <Route path="builder" element={<AgentBuilderEntryPage />} />
            <Route path="agents/:agentId/design" element={<AgentBuilderDesignPage />} />
            <Route path="agents/:agentId/run" element={<AgentRunPage />} />
            <Route path="agents/:agentId/runs" element={<RunHistoryPage />} />
            <Route path="benchmark" element={<CompatibilityRedirect pathname="/benchmarks" />} />
            <Route path="benchmarks" element={<BenchmarksPage />} />
            <Route path="benchmarks/:benchmarkId" element={<BenchmarkDetailPage />} />
            <Route path="benchmark-authoring" element={<BenchmarkAuthoringPage />} />
            <Route
              path="benchmark-drafts/:draftId/edit"
              element={<BenchmarkDraftEditPage />}
            />
            <Route path="experiments" element={<ExperimentHistoryPage />} />
            <Route path="experiments/new" element={<ExperimentCreatePage />} />
            <Route
              path="experiments/:experimentId"
              element={<ExperimentMonitorPage />}
            />
            <Route
              path="experiments/:experimentId/report"
              element={<ExperimentReportPage />}
            />
            <Route path="history" element={<RunHistoryPage />} />
            <Route path="runs/:runId/replay" element={<RunReplayPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="help" element={<HelpCenterPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
        <ToastViewport />
      </>
    </ModuleNavSwitchProvider>
  );
}

/** Preserve legal query state while replacing one deterministic legacy route. */
function CompatibilityRedirect({ pathname }: { pathname: string }) {
  const location = useLocation();
  return <Navigate to={{ pathname, search: location.search }} replace />;
}
