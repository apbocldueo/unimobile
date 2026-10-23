import { describe, expect, it } from "vitest";
import {
  parseExperimentHistoryRoute,
  serializeExperimentHistoryRoute,
} from "./experimentHistoryRoute";

describe("Experiment History route", () => {
  it("reconstructs and canonically serializes exact filters and cursor", () => {
    const route = parseExperimentHistoryRoute(
      new URLSearchParams(
        "limit=25&lifecycle=running&catalogEntryId=catalog.one"
        + "&agentId=agent-one&acceptedFrom=10&acceptedBefore=20"
        + "&cursor=opaque-v2",
      ),
    );
    expect(route).toEqual({
      mode: "history",
      limit: 25,
      cursor: "opaque-v2",
      filters: {
        lifecycle: "running",
        catalogEntryId: "catalog.one",
        agentId: "agent-one",
        acceptedFrom: 10,
        acceptedBefore: 20,
      },
    });
    if (route.mode !== "history") throw new Error("expected valid route");
    expect(serializeExperimentHistoryRoute(route).toString()).toBe(
      "limit=25&lifecycle=running&catalogEntryId=catalog.one"
      + "&agentId=agent-one&acceptedFrom=10&acceptedBefore=20"
      + "&cursor=opaque-v2",
    );
  });

  it("rejects duplicate, unknown, blank, unsafe, and inverted values", () => {
    for (const query of [
      "agentId=one&agentId=two",
      "unknown=value",
      "catalogEntryId=",
      "acceptedFrom=01",
      "acceptedFrom=20&acceptedBefore=10",
      "agentId=../unsafe",
      "limit=101",
      "lifecycle=unknown",
    ]) {
      expect(
        parseExperimentHistoryRoute(new URLSearchParams(query)).mode,
      ).toBe("invalid");
    }
  });

  it("keeps the unfiltered route backward-compatible", () => {
    expect(parseExperimentHistoryRoute(new URLSearchParams())).toEqual({
      mode: "history",
      limit: 50,
      cursor: null,
      filters: {},
    });
  });
});
