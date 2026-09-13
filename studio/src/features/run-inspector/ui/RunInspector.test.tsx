import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createReplayEnvelopeFixture } from "@/entities/replay";
import { projectReplay, type ReplayProjection } from "@/entities/run";
import { RunInspector, type RunInspectorOverview, type RunInspectorViewModel } from "./RunInspector";

/** Build the bounded overview shared by Inspector UI tests. */
function overview(): RunInspectorOverview {
  return {
    agentStatus: "success",
    benchmarkOutcome: "fail",
    failureTarget: {
      kind: "benchmark_evaluation",
      cursor: 1,
      activationId: null,
      nodePath: null,
      label: "Benchmark evaluation failed",
    },
    location: "Benchmark evaluation",
    reason: "目标状态未满足",
    reasonSource: "benchmark_phase",
    counts: { steps: 1, activations: 1, interactions: 1 },
    milestones: [{ cursor: 1, kind: "complete", label: "reason · complete", activationId: "activation-reason" }],
    evidence: { graphState: "available", screenshotState: "missing", integrityState: "complete" },
  };
}

/** Build a detached Inspector view model over one factual projection. */
function viewModel(projection?: ReplayProjection): RunInspectorViewModel {
  const envelope = createReplayEnvelopeFixture();
  return {
    runId: envelope.runId,
    snapshot: envelope.snapshot,
    projection: projection ?? projectReplay(envelope),
    provenance: envelope.provenance,
    agentStatus: envelope.result.status,
    kernelStatus: envelope.result.kernelStatus,
    benchmarkOutcome: envelope.benchmark?.outcome ?? null,
    resultError: "",
    availability: envelope.availability,
    artifactUrl: (artifactId) => `/artifacts/${artifactId}`,
    loadArtifactText: null,
    readOnlyLabel: "只读 Replay",
    terminalVisible: true,
    overview: overview(),
  };
}

/** Own selected activation state like the Live/Replay workbench. */
function InspectorHarness({ model }: { model: RunInspectorViewModel }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <RunInspector
      viewModel={model}
      selectedActivationId={selected}
      onSelectActivation={setSelected}
      onJumpToFailure={vi.fn()}
      onJumpToMoment={vi.fn()}
    />
  );
}

describe("RunInspector", () => {
  afterEach(() => cleanup());

  it("opens on a persistent causal story instead of technical event tails", () => {
    render(<InspectorHarness model={viewModel()} />);
    expect(screen.getByRole("tab", { name: "过程", selected: true })).not.toBeNull();
    expect(screen.getByText("交互 1")).not.toBeNull();
    expect(screen.getByText("选择下一步行动")).not.toBeNull();
    expect(screen.getByText("运行已经结束")).not.toBeNull();
    expect(screen.queryByText("reason · complete")).toBeNull();
    expect(screen.queryByText("focused-replay-fixture")).toBeNull();
    expect(screen.queryByText("activation-reason")).toBeNull();
  });

  it("separates component inputs and outputs and keeps Prompt content hidden", () => {
    const envelope = createReplayEnvelopeFixture();
    envelope.moments[0]!.payload = { task: "打开设置", observation: "首页", prompt: "secret prompt" };
    envelope.moments[1]!.payload = { decision: "点击设置", prompt: "secret prompt" };
    const projection = projectReplay(envelope);
    projection.debugByActivationId["activation-reason"] = [{
      schemaVersion: 1,
      debugId: "debug-reason",
      runId: envelope.runId,
      nodePath: "reason",
      activationId: "activation-reason",
      componentIdentity: "reasoning",
      role: "reasoning",
      stage: "complete",
      task: "打开设置",
      inputSummary: { observation: "首页" },
      outputSummary: { decision: "点击设置" },
      durationMs: 12,
      error: "",
      usage: {},
      artifactIds: [],
      evidenceRefs: {},
      availability: { debugPayload: "available", modelResponse: "not_captured", prompt: "hidden" },
      diagnostics: [],
    }];
    render(<InspectorHarness model={viewModel(projection)} />);
    fireEvent.click(screen.getByRole("button", { name: /判断.*选择下一步行动/s }));
    expect(screen.getByRole("tab", { name: "组件详情", selected: true })).not.toBeNull();
    const inputs = screen.getByRole("heading", { name: "输入" }).closest("section")!;
    const outputs = screen.getByRole("heading", { name: "输出" }).closest("section")!;
    expect(within(inputs).getByText("首页")).not.toBeNull();
    expect(within(outputs).getByText("点击设置")).not.toBeNull();
    expect(screen.queryByText("secret prompt")).toBeNull();
  });

  it("locks historical detail while retaining a clear return-to-current action", () => {
    render(<InspectorHarness model={viewModel()} />);
    fireEvent.click(screen.getByRole("button", { name: /判断.*选择下一步行动/s }));
    expect(screen.getByText(/正在查看历史步骤/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "回到当前" }));
    expect(screen.queryByText(/正在查看历史步骤/)).toBeNull();
  });

  it("keeps identities, raw payload and Prompt availability behind technical detail", () => {
    render(<InspectorHarness model={viewModel()} />);
    fireEvent.click(screen.getByRole("button", { name: /判断.*选择下一步行动/s }));
    fireEvent.click(screen.getByRole("tab", { name: "技术详情" }));
    expect(screen.getByText("activation-reason").closest("details")?.open).toBe(false);
    fireEvent.click(screen.getByText("组件定义与 exact activation"));
    expect(screen.getByText("activation-reason").closest("details")?.open).toBe(true);
    fireEvent.click(screen.getByText("证据与安全原始数据"));
    expect(screen.getByText("Prompt")).not.toBeNull();
    expect(screen.getAllByText("not_captured").length).toBeGreaterThan(0);
  });

  it("shows Action Executor effect results in output detail", () => {
    const envelope = createReplayEnvelopeFixture();
    envelope.moments = envelope.moments.map((moment) => {
      const payload: Record<string, string> = moment.kind === "start"
        ? { action: "tap", target: "设置" }
        : { result: "success" };
      return {
        ...moment,
        role: "ActionExecutor",
        component: "action_executor",
        nodeId: "act",
        nodePath: "act",
        activationId: "activation-act",
        payload,
      };
    });
    const projection = projectReplay(envelope);
    render(<InspectorHarness model={viewModel(projection)} />);
    fireEvent.click(screen.getByRole("button", { name: /行动.*执行设备动作/s }));
    expect(screen.getByText("已确认：device_input")).not.toBeNull();
    expect(screen.getByText(/tap 已执行/)).not.toBeNull();
  });
});
