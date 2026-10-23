import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import {
  createReplayEnvelopeFixture,
  type ReplayEnvelope,
} from "@/entities/replay";
import { useReplayPlaybackStore } from "@/features/trajectory-replay";
import { ThreePaneReplayWorkbench } from "./ThreePaneReplayWorkbench";

const OriginalResizeObserver = globalThis.ResizeObserver;

beforeAll(() => {
  globalThis.ResizeObserver = class ResizeObserver {
    /** Register one observed element for the XYFlow test shell. */
    observe(): void {}

    /** Stop observing one element for the XYFlow test shell. */
    unobserve(): void {}

    /** Release the inert XYFlow test observer. */
    disconnect(): void {}
  };
});

afterAll(() => {
  globalThis.ResizeObserver = OriginalResizeObserver;
});

/** Build a complete fake evidence envelope with an external component and no screenshot. */
function fakeEnvelope(): ReplayEnvelope {
  return {
    schemaVersion: 1,
    runId: "fake-workbench-run",
    importedAt: 1,
    provenance: "fake_contract_fixture",
    evidenceOrigin: {
      schemaVersion: 1,
      acquisition: "contract_fixture",
      environment: "fake_device",
      deviceProfileId: "fixture-android",
      deviceChecks: [],
      realDeviceEvidence: false,
    },
    integrityState: "complete",
    snapshot: {
      agentId: "research-agent",
      revisionId: "revision-1",
      contractVersion: "1.1",
      canonicalHash: null,
      graphStatus: "not_captured",
      agentGraph: null,
      graphNodes: [],
      graphEdges: [],
      presentation: null,
      sourceMap: [],
      providerIdentities: [],
    },
    result: {
      status: "success",
      kernelStatus: "success",
      error: "",
      stepCount: 1,
      activationCount: 1,
      interactionCount: 1,
      usage: {},
    },
    moments: [
      {
        momentId: "moment-1",
        causalIndex: 0,
        sourceKind: "agent_graph",
        sourceSequence: 1,
        timestamp: 1,
        phase: "graph_kernel",
        kind: "start",
        role: "example.external.audit",
        component: "external_audit",
        nodeId: "external",
        nodePath: "subgraph/external",
        activationId: "activation-external",
        parentActivationId: "",
        loopPath: "research-loop",
        loopIteration: 1,
        interactionStep: 1,
        durationMs: null,
        payload: { task: "inspect settings" },
        observationId: null,
        actionId: null,
        artifactIds: [],
      },
      {
        momentId: "moment-2",
        causalIndex: 1,
        sourceKind: "agent_graph",
        sourceSequence: 2,
        timestamp: 2,
        phase: "graph_kernel",
        kind: "complete",
        role: "example.external.audit",
        component: "external_audit",
        nodeId: "external",
        nodePath: "subgraph/external",
        activationId: "activation-external",
        parentActivationId: "",
        loopPath: "research-loop",
        loopIteration: 1,
        interactionStep: 1,
        durationMs: 12,
        payload: {
          modelResponse: "Completed audit",
          debugPayload: { branch: "done" },
        },
        observationId: "observation-1",
        actionId: null,
        artifactIds: [],
      },
    ],
    observations: [
      {
        observationId: "observation-1",
        sequence: 1,
        interactionStep: 1,
        screenshotArtifactId: null,
        uiArtifactId: null,
        width: 1080,
        height: 2400,
        platform: "fake",
        deviceId: "device-sha256:fixture",
        overlay: [],
      },
    ],
    actions: [],
    benchmark: {
      experimentId: "experiment-1",
      taskId: "task-1",
      agentId: "research-agent",
      repeat: 0,
      outcome: "fail",
      identities: {},
      phases: [
        {
          phase: "evaluation",
          status: "failure",
          durationMs: 2,
          errorCode: "",
          message: "",
          evidence: { isPass: false },
        },
      ],
      evaluation: { isPass: false },
    },
    artifacts: [],
    availability: {
      agentGraph: { state: "not_captured", reasonCode: "", detail: "" },
      screenshots: { state: "missing", reasonCode: "", detail: "" },
      uiXml: { state: "available", reasonCode: "", detail: "" },
      modelResponse: { state: "available", reasonCode: "", detail: "" },
      prompt: { state: "excluded", reasonCode: "", detail: "" },
      debugPayload: { state: "available", reasonCode: "", detail: "" },
    },
    integrity: [],
  };
}

describe("ThreePaneReplayWorkbench", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    window.localStorage.clear();
    useReplayPlaybackStore.setState({
      runId: null,
      cursor: -1,
      maxCursor: -1,
      isPlaying: false,
      speed: 1,
      autoFollow: true,
      lockedActivationId: null,
      selectedMomentId: null,
    });
  });

  it("composes honest graph, phone, inspector, and independent lanes", () => {
    render(<ThreePaneReplayWorkbench envelope={fakeEnvelope()} />);
    expect(screen.getByLabelText("Replay AgentGraph").textContent).toContain(
      "graph_snapshot_unavailable",
    );
    expect(screen.getByLabelText("Virtual Phone")).not.toBeNull();
    expect(screen.getByLabelText("Run Inspector")).not.toBeNull();
    expect(screen.getByLabelText("Replay timeline")).not.toBeNull();
    expect(screen.getAllByText("success").length).toBeGreaterThan(0);
    expect(screen.getAllByText("fail").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("tab", { name: "技术详情" }));
    fireEvent.click(screen.getByText("运行身份与完整性"));
    expect(screen.getByText(/Supporting fake-device fixture/)).not.toBeNull();
    expect(screen.getAllByText("fake_device").length).toBeGreaterThan(0);
    expect(screen.getByText("false")).not.toBeNull();
  });

  it("explains that real-Android Replay is historical rather than fresh", () => {
    const envelope = fakeEnvelope();
    envelope.provenance = "native_benchmark_task_run";
    envelope.evidenceOrigin = {
      ...envelope.evidenceOrigin,
      acquisition: "replay_projection",
      environment: "real_android",
    };
    render(<ThreePaneReplayWorkbench envelope={envelope} />);
    fireEvent.click(screen.getByRole("tab", { name: "技术详情" }));
    fireEvent.click(screen.getByText("运行身份与完整性"));
    expect(
      screen.getByText(/Historical projection of a real-Android source/),
    ).not.toBeNull();
    expect(screen.getByText(/not a new fresh-device execution/)).not.toBeNull();
  });

  it("shows external activation evidence and missing current screenshot", () => {
    const envelope = fakeEnvelope();
    envelope.moments[1]!.payload = {
      modelResponse: "Completed audit",
      debugPayload: { branch: "done" },
      prompt: "secret prompt text",
    };
    render(<ThreePaneReplayWorkbench envelope={envelope} />);
    act(() => useReplayPlaybackStore.getState().seek(1));
    fireEvent.click(screen.getByRole("tab", { name: "技术详情" }));
    fireEvent.click(screen.getByText("组件定义与 exact activation"));
    fireEvent.click(screen.getByText("证据与安全原始数据"));
    expect(screen.getAllByText("example.external.audit").length).toBeGreaterThan(0);
    expect(screen.getAllByText("当前截图缺失").length).toBeGreaterThan(0);
    expect(screen.getByText("完整模型响应")).not.toBeNull();
    expect(screen.getByText("excluded")).not.toBeNull();
    expect(screen.queryByText("secret prompt text")).toBeNull();
  });

  it("omits the Benchmark lane entirely for an Agent-only Replay", () => {
    const envelope = fakeEnvelope();
    envelope.benchmark = null;
    render(<ThreePaneReplayWorkbench envelope={envelope} />);
    expect(screen.queryByText("Benchmark")).toBeNull();
    expect(screen.getByText("精确事件 · 2")).not.toBeNull();
  });

  it("keeps exact generic topology visible without capability-only disclosure controls", () => {
    const envelope = createReplayEnvelopeFixture();
    envelope.result.status = "failure";
    envelope.moments[1]!.kind = "failure";
    render(<ThreePaneReplayWorkbench envelope={envelope} />);
    expect(screen.queryByRole("button", { name: "运行路径" })).toBeNull();
    expect(screen.queryByRole("button", { name: "关系全图" })).toBeNull();
    expect(screen.getAllByText("observe").length).toBeGreaterThan(0);
    expect(screen.getAllByText("reason").length).toBeGreaterThan(0);
    expect(screen.getAllByText("act").length).toBeGreaterThan(0);
  });

  it("survives light and dark theme changes without storing Replay facts", () => {
    const rendered = render(<ThreePaneReplayWorkbench envelope={fakeEnvelope()} />);
    document.documentElement.dataset.zxTheme = "light";
    rendered.rerender(<ThreePaneReplayWorkbench envelope={fakeEnvelope()} />);
    document.documentElement.dataset.zxTheme = "dark";
    rendered.rerender(<ThreePaneReplayWorkbench envelope={fakeEnvelope()} />);
    expect(window.localStorage.getItem("fake-workbench-run")).toBeNull();
    expect(screen.getAllByText("research-agent").length).toBeGreaterThan(0);
  });

  it("migrates the bounded Replay pane preference to the shared workbench key", () => {
    window.localStorage.setItem(
      "zx-studio-replay-panes-v1",
      JSON.stringify({ left: 45, middle: 25, right: 30 }),
    );
    render(<ThreePaneReplayWorkbench envelope={fakeEnvelope()} />);
    expect(
      JSON.parse(
        window.localStorage.getItem("zx-studio-workbench-panes-v3") ?? "{}",
      ),
    ).toEqual({ left: 45, middle: 25, right: 30 });
    act(() => screen.getByRole("button", { name: "重置布局" }).click());
    expect(window.localStorage.getItem("zx-studio-workbench-panes-v3")).toBeNull();
    expect(window.localStorage.getItem("zx-studio-replay-panes-v1")).toBeNull();
  });
});
