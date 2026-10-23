import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { PhoneFrameProjection } from "@/entities/run";
import { VirtualPhone } from "./VirtualPhone";

/** Build one explicit phone-frame projection for UI tests. */
function phoneFrame(state: PhoneFrameProjection["state"]): PhoneFrameProjection {
  return {
    state,
    observation: {
      observationId: "observation-1",
      sequence: 1,
      interactionStep: 2,
      screenshotArtifactId: state === "available" ? "artifact-1" : null,
      uiArtifactId: null,
      width: 1080,
      height: 2400,
      platform: "fake",
      deviceId: "device-sha256:fixture",
      overlay: [],
    },
    screenshotArtifactId: state === "available" ? "artifact-1" : null,
    isHistorical: false,
  };
}

describe("VirtualPhone", () => {
  afterEach(() => cleanup());

  it("replaces unavailable screenshots with a compact truthful state", () => {
    render(
      <VirtualPhone frame={phoneFrame("missing")} latestAction={null} resolveArtifact={() => null} />,
    );
    expect(screen.getByText("当前截图缺失")).not.toBeNull();
    expect(screen.getByText(/不会用历史画面冒充当前证据/)).not.toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("falls back to corrupt after an available image fails to load", () => {
    render(
      <VirtualPhone
        frame={phoneFrame("available")}
        latestAction={null}
        resolveArtifact={() => ({ url: "/artifact.png", availability: "available" })}
      />,
    );
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByText("截图证据损坏")).not.toBeNull();
  });
});
