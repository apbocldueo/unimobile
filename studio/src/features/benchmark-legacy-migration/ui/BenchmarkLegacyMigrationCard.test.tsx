import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkLegacyMigrationConfirmFixture,
  benchmarkLegacyMigrationPreviewFixture,
} from "@/entities/benchmark-authoring";
import { useBenchmarkLegacyMigrationStore } from "../model/benchmarkLegacyMigration.store";
import { BenchmarkLegacyMigrationCard } from "./BenchmarkLegacyMigrationCard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => useBenchmarkLegacyMigrationStore.getState().reset());

/** Return a fresh strict JSON response for the fake migration backend. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Render the disposable migration card with an isolated server-state cache. */
function renderCard(onConfirmed = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <BenchmarkLegacyMigrationCard onConfirmed={onConfirmed} />
    </QueryClientProvider>,
  );
  return { ...view, onConfirmed, queryClient };
}

/** Select one browser-owned JSON File with a deterministic text reader. */
function selectLegacyFile(sourceText = "[]") {
  const file = new File([sourceText], "legacy.json", { type: "application/json" });
  Object.defineProperty(file, "text", {
    value: vi.fn().mockResolvedValue(sourceText),
  });
  fireEvent.change(screen.getByLabelText("Legacy JSON file"), {
    target: { files: [file] },
  });
}

describe("BenchmarkLegacyMigrationCard", () => {
  it("runs explicit Preview, Confirm, authoritative cache adoption, and navigation", async () => {
    const requests: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      requests.push(JSON.parse(String(init?.body)));
      return Promise.resolve(requests.length === 1
        ? jsonResponse(benchmarkLegacyMigrationPreviewFixture())
        : jsonResponse(benchmarkLegacyMigrationConfirmFixture(), 201));
    }));
    const { onConfirmed, queryClient } = renderCard();
    const draftListKey = ["studio", "benchmark-authoring", "drafts", { limit: 30 }];
    queryClient.setQueryData(draftListKey, { schemaVersion: 1, items: [], nextCursor: null });
    selectLegacyFile('[{"id":"task-1"}]');
    await waitFor(() => expect((screen.getByRole("button", { name: "Preview migration" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Preview migration" }));
    expect(await screen.findByLabelText("Migration preview")).toBeTruthy();
    const confirmed = benchmarkLegacyMigrationConfirmFixture();
    expect(queryClient.getQueryData(["studio", "benchmark-authoring", "draft", confirmed.draft.draftId])).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Confirm migration" }));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1));
    expect(requests[0]).toMatchObject({ sourceText: '[{"id":"task-1"}]' });
    expect(requests[0]).not.toHaveProperty("sourcePath");
    expect(queryClient.getQueryData(["studio", "benchmark-authoring", "draft", confirmed.draft.draftId])).toBeTruthy();
    expect(queryClient.getQueryState(draftListKey)?.isInvalidated).toBe(true);
  });

  it("invalidates Preview authority immediately after any target edit", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(benchmarkLegacyMigrationPreviewFixture())));
    renderCard();
    selectLegacyFile();
    await waitFor(() => expect((screen.getByRole("button", { name: "Preview migration" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Preview migration" }));
    await screen.findByLabelText("Migration preview");
    fireEvent.change(screen.getByLabelText("Migration title"), { target: { value: "Changed title" } });
    expect(screen.queryByLabelText("Migration preview")).toBeNull();
    expect(useBenchmarkLegacyMigrationStore.getState().preview).toBeNull();
  });

  it("renders duplicate diagnostics and never enables Confirm", async () => {
    const rejected = benchmarkLegacyMigrationPreviewFixture();
    rejected.confirmable = false;
    rejected.previewFingerprint = null;
    rejected.candidateDocumentFingerprint = null;
    rejected.diagnostics = [{
      code: "migration.task.duplicate_id",
      severity: "error",
      message: "Duplicate task ID at source index 72.",
      sourceIndex: 72,
      fieldPath: ["id"],
      taskId: "AndroidWorld_72",
    }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(rejected)));
    renderCard();
    selectLegacyFile();
    await waitFor(() => expect((screen.getByRole("button", { name: "Preview migration" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Preview migration" }));
    expect(await screen.findByText(/Duplicate task ID/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Confirm migration" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("reuses exact Confirm command after response uncertainty", async () => {
    const confirmBodies: string[] = [];
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      calls += 1;
      if (String(url).endsWith("/preview")) return Promise.resolve(jsonResponse(benchmarkLegacyMigrationPreviewFixture()));
      confirmBodies.push(String(init?.body));
      if (calls === 2) return Promise.reject(new Error("connection lost"));
      return Promise.resolve(jsonResponse(benchmarkLegacyMigrationConfirmFixture(false), 200));
    }));
    const { onConfirmed } = renderCard();
    selectLegacyFile();
    await waitFor(() => expect((screen.getByRole("button", { name: "Preview migration" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Preview migration" }));
    await screen.findByLabelText("Migration preview");
    fireEvent.click(screen.getByRole("button", { name: "Confirm migration" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/结果未确认/);
    fireEvent.click(screen.getByRole("button", { name: "Confirm migration" }));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1));
    expect(JSON.parse(confirmBodies[0]).clientRequestId).toBe(JSON.parse(confirmBodies[1]).clientRequestId);
  });

  it("requires re-Preview after server conflict and disposes state on unmount", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) =>
      String(url).endsWith("/preview")
        ? Promise.resolve(jsonResponse(benchmarkLegacyMigrationPreviewFixture()))
        : Promise.resolve(jsonResponse({ schemaVersion: 1, error: { code: "stale", message: "stale" } }, 409)),
    ));
    const view = renderCard();
    selectLegacyFile();
    await waitFor(() => expect((screen.getByRole("button", { name: "Preview migration" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Preview migration" }));
    await screen.findByLabelText("Migration preview");
    fireEvent.click(screen.getByRole("button", { name: "Confirm migration" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/必须重新 Preview/);
    expect(screen.queryByLabelText("Migration preview")).toBeNull();
    view.unmount();
    expect(useBenchmarkLegacyMigrationStore.getState().sourceFile).toBeNull();
  });
});
