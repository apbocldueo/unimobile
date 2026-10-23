import { afterEach, describe, expect, it } from "vitest";
import { Position, type FinalConnectionState } from "@xyflow/react";
import { endedConnection } from "./connectionAttempt";

const from = { nodeId: "reason", id: "reason:output:action", type: "source" as const, position: Position.Right, x: 0, y: 0, width: 24, height: 24 };
const target = { ...from, nodeId: "output", id: "output:input:connection", type: "target" as const };
const rejected = { isValid: false, fromHandle: from, toHandle: target } as FinalConnectionState;

afterEach(() => { document.body.replaceChildren(); });

describe("rejected connection endpoints", () => {
  it("orients forward and reverse drags without changing the graph", () => {
    const expected = { source: "reason", sourceHandle: from.id, target: "output", targetHandle: target.id };
    expect(endedConnection(new MouseEvent("mouseup"), rejected)).toEqual(expected);
    expect(endedConnection(new MouseEvent("mouseup"), { ...rejected, fromHandle: target, toHandle: from })).toEqual(expected);
  });
  it("recovers invalid and keyboard-click targets from rendered handles", () => {
    const handle = document.createElement("div");
    handle.dataset.nodeid = target.nodeId;
    handle.dataset.handleid = target.id;
    handle.className = "target";
    document.body.append(handle);
    const event = new MouseEvent("click", { bubbles: true });
    handle.dispatchEvent(event);
    expect(endedConnection(event, { ...rejected, fromHandle: null, toHandle: null }, from)).toEqual({ source: "reason", sourceHandle: from.id, target: "output", targetHandle: target.id });
  });
  it("explains same-direction ports but quietly cancels empty space and the start port", () => {
    expect(endedConnection(new MouseEvent("mouseup"), { ...rejected, toHandle: null })).toBeNull();
    expect(endedConnection(new MouseEvent("mouseup"), { ...rejected, toHandle: from })).toBeNull();
    expect(endedConnection(new MouseEvent("mouseup"), { ...rejected, toHandle: { ...from, nodeId: "other" } })).toContain("输出端口连接到输入端口");
  });
});
