import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import {
  benchmarkArchiveFixture,
  benchmarkAuthoringRevisionFixture,
  benchmarkExportResultFixture,
  benchmarkPackageExportFixture,
  benchmarkPackageRevisionFixtureId,
  benchmarkPackageRevisionPageFixture,
  benchmarkPublicationResultFixture,
} from "@/entities/benchmark-authoring";
import { BenchmarkReleaseView } from "./BenchmarkReleaseView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Return a fresh JSON response for one fake release exchange. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Render one URL-owned Release workspace with a clean exact-current baseline. */
function renderRelease() {
  const revision = benchmarkAuthoringRevisionFixture();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          `/benchmark-drafts/edit?mode=release&packageRevisionId=${benchmarkPackageRevisionFixtureId}`,
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <BenchmarkReleaseView
          revision={revision}
          gateInput={{
            dirty: false,
            hasBufferError: false,
            hasUnappliedBuffer: false,
            baselineRevisionId: revision.revisionId,
            queryCurrentRevisionId: revision.revisionId,
            conflictRevisionId: null,
            remoteMayBeNewer: false,
            peerPending: false,
          }}
          onPendingChange={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Benchmark Release view", () => {
  it("deep-links one immutable candidate and keeps Publish and Export explicit", async () => {
    let published = false;
    let exported = false;
    const fetchMock = vi.fn().mockImplementation((request: string, init?: RequestInit) => {
      const url = String(request);
      if (url.includes("/package-revisions?") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(jsonResponse(benchmarkPackageRevisionPageFixture({
          published,
          exported,
        })));
      }
      if (url.endsWith("/publications") && init?.method === "POST") {
        published = true;
        return Promise.resolve(jsonResponse(benchmarkPublicationResultFixture(), 201));
      }
      if (url.endsWith("/exports") && init?.method === "POST") {
        exported = true;
        return Promise.resolve(jsonResponse(benchmarkExportResultFixture(), 201));
      }
      if (url.endsWith("/content") && init?.method === "HEAD") {
        const descriptor = benchmarkPackageExportFixture();
        return Promise.resolve(new Response(null, {
          status: 200,
          headers: {
            "Content-Type": descriptor.archiveMediaType,
            "Content-Length": String(descriptor.size),
            "Content-Disposition": `attachment; filename="${descriptor.filename}"`,
            "X-Content-SHA256": benchmarkArchiveFixture,
          },
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", vi.fn(() => true));
    const nativeDownload = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderRelease();

    expect(await screen.findByText("Release authority")).toBeTruthy();
    expect(screen.getByText(/executionEvidence=false，realDeviceEvidence=false/))
      .toBeTruthy();
    expect(fetchMock.mock.calls.filter((call) => call[1]?.method === "POST"))
      .toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByRole("button", { name: "Published" })).toBeTruthy();
    expect(screen.getByText(/managed Catalog/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(await screen.findByRole("button", { name: "Exported" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() => expect(nativeDownload).toHaveBeenCalledOnce());
    expect(await screen.findByText(/不会进入 React state/)).toBeTruthy();
  });

  it("keeps prior immutable revisions inspectable while dirty state blocks Freeze", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(
      benchmarkPackageRevisionPageFixture(),
    )));
    const revision = benchmarkAuthoringRevisionFixture();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter
          initialEntries={[
            `/benchmark-drafts/edit?mode=release&packageRevisionId=${benchmarkPackageRevisionFixtureId}`,
          ]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <BenchmarkReleaseView
            revision={revision}
            gateInput={{
              dirty: true,
              hasBufferError: false,
              hasUnappliedBuffer: false,
              baselineRevisionId: revision.revisionId,
              queryCurrentRevisionId: revision.revisionId,
              conflictRevisionId: null,
              remoteMayBeNewer: false,
              peerPending: false,
            }}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Release authority")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Freeze current" }) as HTMLButtonElement).disabled)
      .toBe(true);
    expect(screen.getByText("存在未保存的本地修改。")).toBeTruthy();
  });
});
