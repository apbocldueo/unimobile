import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/app/shell/AppShell";
import { ModuleNavSwitchProvider } from "@/app/shell/ModuleNavSwitchContext";
import { ToastViewport } from "@/app/shell/ToastViewport";

import { AgentStudioPage } from "@/features/agent-studio/AgentStudioPage";
import { BenchmarkSuitePage } from "@/features/benchmark-suite/BenchmarkSuitePage";
import { RunHistoryPage } from "@/features/run-history/RunHistoryPage";
import { HelpCenterPage } from "@/features/help-center/HelpCenterPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StudioHomePage } from "@/features/studio-home/StudioHomePage";

export function AppRoutes() {
  return (
    <ModuleNavSwitchProvider>
      <>
        <Routes>
          <Route path="/" element={<StudioHomePage />} />
          <Route element={<AppShell />}>
            <Route path="builder" element={<AgentStudioPage />} />
            <Route path="benchmark" element={<BenchmarkSuitePage />} />
            <Route path="history" element={<RunHistoryPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="help" element={<HelpCenterPage />} />
          </Route>
        </Routes>
        <ToastViewport />
      </>
    </ModuleNavSwitchProvider>
  );
}
