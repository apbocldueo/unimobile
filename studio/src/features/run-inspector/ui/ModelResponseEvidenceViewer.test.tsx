import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DebugEvidenceReference } from "@/entities/run";
import { ModelResponseEvidenceViewer } from "./ModelResponseEvidenceViewer";

const reference: DebugEvidenceReference = {
  schemaVersion: 1,
  kind: "model_response",
  artifactId: `artifact-${"a".repeat(32)}`,
  availability: "truncated",
  contentType: "text/plain",
  size: 12,
  originalSize: 20,
  sha256: `sha256:${"b".repeat(64)}`,
  provenance: "component_invocation",
  causalIdentity: "debug-1",
  hidden: false,
};

afterEach(() => cleanup());

describe("ModelResponseEvidenceViewer", () => {
  it("loads typed evidence lazily and labels truncated content", async () => {
    const loadText = vi.fn().mockResolvedValue("full model response");
    render(
      <ModelResponseEvidenceViewer
        reference={reference}
        availability="truncated"
        loadText={loadText}
      />,
    );
    expect(loadText).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "加载完整响应" }));
    await waitFor(() => {
      expect(screen.getByText("full model response")).not.toBeNull();
    });
    expect(screen.getByText(/截断内容/)).not.toBeNull();
  });

  it("does not guess a legacy model artifact by ordinal", () => {
    render(
      <ModelResponseEvidenceViewer
        reference={null}
        availability="available"
        loadText={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/不会按 artifact 顺序猜测/)).not.toBeNull();
  });
});
