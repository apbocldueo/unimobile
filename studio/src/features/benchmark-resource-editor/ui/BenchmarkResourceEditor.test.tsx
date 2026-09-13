import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkAuthoringRevisionFixture,
  benchmarkDraftDetailFixture,
  type BenchmarkAuthoringContentCommandResult,
  type BenchmarkAuthoringResource,
  type BenchmarkAuthoringRevision,
} from "@/entities/benchmark-authoring";
import {
  BenchmarkResourceEditor,
  type BenchmarkResourceMutationGate,
} from "@/features/benchmark-resource-editor";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const allowedGate: BenchmarkResourceMutationGate = {
  allowed: true,
  code: "allowed",
  message: "资源命令可执行。",
};

/** Return a strict JSON response for one deterministic fake exchange. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Advance one immutable revision and project one content command response. */
function contentResult(
  current: BenchmarkAuthoringRevision,
  operation: "upload" | "replace" | "remove",
  resource: BenchmarkAuthoringResource,
): BenchmarkAuthoringContentCommandResult {
  const nextOrdinal = current.ordinal + 1;
  const revisionId = `benchmark-authoring-revision-${String(nextOrdinal).padStart(32, "0")}`;
  const resources = current.document.resources.filter((item) =>
    operation === "replace" || operation === "remove"
      ? item.id !== resource.id
      : true);
  if (operation !== "remove") resources.push(resource);
  resources.sort((left, right) => left.path.localeCompare(right.path));
  const revision: BenchmarkAuthoringRevision = {
    ...benchmarkAuthoringRevisionFixture("edit"),
    revisionId,
    draftId: current.draftId,
    ordinal: nextOrdinal,
    parentRevisionId: current.revisionId,
    document: { ...current.document, resources },
    createdAt: current.createdAt + nextOrdinal,
  };
  return {
    schemaVersion: 1,
    operation,
    created: true,
    draft: {
      ...benchmarkDraftDetailFixture().draft,
      currentRevisionId: revision.revisionId,
      updatedAt: revision.createdAt,
    },
    revision,
    resource: operation === "remove" ? null : resource,
    removedResourceId: operation === "remove" ? resource.id : null,
  };
}

/** Install an immutable no-device content/HEAD service over browser fetch. */
function installResourceBackend(uncertainAttempts = 0) {
  let current = benchmarkAuthoringRevisionFixture();
  let missingInitial = true;
  let commandAttempts = 0;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn().mockImplementation(
    async (request: string, init?: RequestInit) => {
      const url = String(request);
      requests.push({ url, init });
      if (init?.method === "HEAD") {
        if (missingInitial && url.includes("fixture-asset")) {
          return new Response(null, { status: 404 });
        }
        const selected = current.document.resources.find((item) =>
          url.includes(encodeURIComponent(item.id)));
        if (!selected) return new Response(null, { status: 404 });
        return new Response(null, {
          status: 200,
          headers: {
            "Content-Type": selected.mediaType,
            "Content-Length": String(selected.size),
            "Content-Disposition": `attachment; filename="${selected.id}.bin"`,
          },
        });
      }
      if (url.endsWith(`/studio/benchmark-authoring/drafts/${current.draftId}`)) {
        return jsonResponse({
          schemaVersion: 1,
          draft: {
            ...benchmarkDraftDetailFixture().draft,
            currentRevisionId: current.revisionId,
          },
          currentRevision: current,
        });
      }
      const parsed = new URL(url, "http://studio.local");
      const operation = parsed.pathname.endsWith("/upload")
        ? "upload"
        : parsed.pathname.endsWith("/replace")
          ? "replace"
          : parsed.pathname.endsWith("/remove")
            ? "remove"
            : null;
      if (!operation) throw new Error(`Unexpected request: ${url}`);
      commandAttempts += 1;
      if (commandAttempts <= uncertainAttempts) {
        return jsonResponse({
          schemaVersion: 1,
          error: {
            code: "benchmark.authoring.fixture_uncertain",
            message: "Injected uncertain content response",
            currentRevisionId: null,
          },
        }, 503);
      }
      const resourceId = decodeURIComponent(parsed.pathname.split("/").at(-2)!);
      const existing = current.document.resources.find((item) => item.id === resourceId);
      const body = init?.body as File | undefined;
      const resource: BenchmarkAuthoringResource = operation === "upload"
        ? {
            id: resourceId,
            kind: parsed.searchParams.get("kind") as "asset" | "ground_truth",
            path: parsed.searchParams.get("path")!,
            mediaType: String(new Headers(init?.headers).get("Content-Type")),
            sha256: `sha256:${"1".repeat(64)}`,
            size: body?.size ?? 0,
            contentIdentity: `benchmark-content-${"2".repeat(64)}`,
          }
        : {
            ...existing!,
            mediaType: operation === "replace"
              ? String(new Headers(init?.headers).get("Content-Type"))
              : existing!.mediaType,
            sha256: operation === "replace"
              ? `sha256:${"3".repeat(64)}`
              : existing!.sha256,
            size: operation === "replace" ? (body?.size ?? 0) : existing!.size,
            contentIdentity: operation === "replace"
              ? `benchmark-content-${"4".repeat(64)}`
              : existing!.contentIdentity,
          };
      const result = contentResult(current, operation, resource);
      current = result.revision;
      if (operation === "replace") missingInitial = false;
      return jsonResponse(result, 201);
    },
  ));
  return requests;
}

/** Render a stateful resource editor that adopts each authoritative revision. */
function renderEditor(
  gate: BenchmarkResourceMutationGate = allowedGate,
  selectionRequest: {
    requestId: number;
    revisionId: string;
    resourceId: string;
  } | null = null,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const success = vi.fn();
  const conflict = vi.fn();
  function Harness() {
    const [revision, setRevision] = useState(benchmarkAuthoringRevisionFixture());
    return (
      <BenchmarkResourceEditor
        revision={revision}
        gate={gate}
        onMutationPendingChange={() => undefined}
        onCommandSuccess={(outcome) => {
          success(outcome);
          setRevision(outcome.currentRevision);
        }}
        onConflict={conflict}
        selectionRequest={selectionRequest}
      />
    );
  }
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return { success, conflict };
}

describe("Benchmark managed resource editor", () => {
  it("accepts only an exact current-revision controlled resource selection", async () => {
    const revision = benchmarkAuthoringRevisionFixture();
    const requests = installResourceBackend();
    renderEditor(allowedGate, {
      requestId: 1,
      revisionId: revision.revisionId,
      resourceId: "fixture-ground-truth",
    });
    expect(await screen.findByRole("heading", { name: "fixture-ground-truth" })).toBeTruthy();
    expect(requests.some((item) =>
      item.init?.method === "HEAD" && item.url.includes("fixture-ground-truth"))).toBe(true);

    cleanup();
    installResourceBackend();
    renderEditor(allowedGate, {
      requestId: 2,
      revisionId: `benchmark-authoring-revision-${"9".repeat(32)}`,
      resourceId: "fixture-ground-truth",
    });
    expect(await screen.findByRole("heading", { name: "fixture-asset" })).toBeTruthy();
  });

  it("uploads file-backed ground truth from a clean baseline without optimism", async () => {
    const requests = installResourceBackend();
    const { success } = renderEditor();
    await screen.findByText(/missing \(404\)/);
    fireEvent.change(screen.getByLabelText("New resource logical ID"), {
      target: { value: "new-ground-truth" },
    });
    fireEvent.change(screen.getByLabelText("New resource kind"), {
      target: { value: "ground_truth" },
    });
    fireEvent.change(screen.getByLabelText("New resource path"), {
      target: { value: "ground_truth/new.json" },
    });
    fireEvent.change(screen.getByLabelText("New resource media type"), {
      target: { value: "application/json" },
    });
    const file = new File(["{\"ok\":true}"], "new.json", {
      type: "application/json",
    });
    fireEvent.change(screen.getByLabelText("New resource file"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload into new revision" }));

    expect(await screen.findByText("new-ground-truth")).toBeTruthy();
    expect(success).toHaveBeenCalledTimes(1);
    const upload = requests.find((item) => item.url.endsWith("kind=ground_truth&path=ground_truth%2Fnew.json"));
    expect(upload?.init?.body).toBe(file);
    expect(new Headers(upload?.init?.headers).has("Content-Length")).toBe(false);
  });

  it("repairs missing bytes, then confirms a logical removal", async () => {
    installResourceBackend();
    renderEditor();
    expect(await screen.findByText(/missing \(404\)/)).toBeTruthy();
    const replacement = new File(["replacement"], "screen.png", {
      type: "image/png",
    });
    fireEvent.change(screen.getByLabelText("Replacement file"), {
      target: { files: [replacement] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Replace in new revision" }));
    expect(await screen.findByText(`sha256:${"3".repeat(64)}`)).toBeTruthy();
    expect(await screen.findByText(/readable/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Remove declaration…" }));
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm logical remove" }));
    await waitFor(() => {
      expect(screen.queryByText(`sha256:${"3".repeat(64)}`)).toBeNull();
    });
    expect(screen.getAllByText("fixture-ground-truth").length).toBeGreaterThan(0);
  });

  it("issues no command and explains a dirty baseline", async () => {
    const requests = installResourceBackend();
    renderEditor({
      allowed: false,
      code: "definition-dirty",
      message: "请先保存或重置定义修改，再执行资源命令。",
    });
    expect(await screen.findByText(/资源命令已阻止/)).toBeTruthy();
    const file = new File(["x"], "x.bin");
    fireEvent.change(screen.getByLabelText("New resource file"), {
      target: { files: [file] },
    });
    const button = screen.getByRole("button", { name: "Upload into new revision" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(requests.filter((item) => item.init?.method === "POST")).toHaveLength(0);
  });

  it("reuses an unchanged uncertain intent and retires it for a new File", async () => {
    const requests = installResourceBackend(2);
    renderEditor();
    await screen.findByText(/missing \(404\)/);
    const input = screen.getByLabelText("Replacement file");
    const firstFile = new File(["first"], "screen.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [firstFile] } });
    fireEvent.click(screen.getByRole("button", { name: "Replace in new revision" }));
    expect(await screen.findByText(/提交结果未确认/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Replace in new revision" }));
    await waitFor(() => {
      expect(requests.filter((item) => item.init?.method === "POST")).toHaveLength(2);
    });
    const secondFile = new File(["second"], "screen.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [secondFile] } });
    fireEvent.click(screen.getByRole("button", { name: "Replace in new revision" }));
    expect(await screen.findByText(`sha256:${"3".repeat(64)}`)).toBeTruthy();
    const commandUrls = requests
      .filter((item) => item.init?.method === "POST")
      .map((item) => new URL(item.url, "http://studio.local"));
    expect(commandUrls[0]!.searchParams.get("clientRequestId")).toBe(
      commandUrls[1]!.searchParams.get("clientRequestId"),
    );
    expect(commandUrls[2]!.searchParams.get("clientRequestId")).not.toBe(
      commandUrls[1]!.searchParams.get("clientRequestId"),
    );
  });

  it("does not hydrate malformed pending responses or mutate inventory optimistically", async () => {
    let release: ((response: Response) => void) | null = null;
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (request: string, init?: RequestInit) => {
        const url = String(request);
        requests.push({ url, init });
        if (init?.method === "HEAD") {
          const resource = benchmarkAuthoringRevisionFixture().document.resources[0]!;
          return Promise.resolve(new Response(null, {
            status: 200,
            headers: {
              "Content-Type": resource.mediaType,
              "Content-Length": String(resource.size),
              "Content-Disposition": `attachment; filename="${resource.id}.bin"`,
            },
          }));
        }
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      },
    ));
    const { success } = renderEditor();
    await screen.findByText(/readable/);
    fireEvent.change(screen.getByLabelText("New resource logical ID"), {
      target: { value: "pending-asset" },
    });
    fireEvent.change(screen.getByLabelText("New resource path"), {
      target: { value: "assets/pending.png" },
    });
    fireEvent.change(screen.getByLabelText("New resource media type"), {
      target: { value: "image/png" },
    });
    fireEvent.change(screen.getByLabelText("New resource file"), {
      target: { files: [new File(["pending"], "pending.png", { type: "image/png" })] },
    });
    const button = screen.getByRole("button", { name: "Upload into new revision" });
    fireEvent.click(button);
    expect(await screen.findByRole("button", { name: "Uploading…" })).toBeTruthy();
    expect(screen.queryByText("pending-asset")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Uploading…" }));
    expect(requests.filter((item) => item.init?.method === "POST")).toHaveLength(1);
    release!(jsonResponse({ schemaVersion: 1, operation: "upload" }));
    await waitFor(() => {
      expect(screen.getAllByText(/结果未确认/).length).toBeGreaterThan(0);
    });
    expect(success).not.toHaveBeenCalled();
    expect(screen.queryByText("pending-asset")).toBeNull();
    expect(screen.getByText(/Revision 1/)).toBeTruthy();
  });
});
