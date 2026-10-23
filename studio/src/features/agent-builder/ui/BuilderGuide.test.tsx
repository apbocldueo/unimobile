import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { BUILDER_GUIDE_PREFERENCE_KEY } from "../model/useBuilderGuide";
import { BuilderGuide } from "./BuilderGuide";

beforeEach(() => window.localStorage.clear());
afterEach(() => cleanup());

describe("Builder canvas guidance", () => {
  it("explains the authoring sequence and can be dismissed and reopened", () => {
    render(<BuilderGuide hasCapabilities={false} hasRelations={false} hasSelection={false} />);

    expect(screen.getByRole("region", { name: "画布操作引导" })).not.toBeNull();
    expect(screen.getByText("点击“添加能力”，依次添加 Perception、Memory、Reasoning、Action Executor，先搭出可运行的观察—记忆—决策—执行闭环。")).not.toBeNull();
    expect(screen.getByText("连出执行闭环")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "隐藏画布提示" }));
    expect(screen.queryByRole("region", { name: "画布操作引导" })).toBeNull();
    expect(window.localStorage.getItem(BUILDER_GUIDE_PREFERENCE_KEY)).toBe("1");

    fireEvent.click(screen.getByRole("button", { name: "画布提示" }));
    expect(screen.getByRole("region", { name: "画布操作引导" })).not.toBeNull();
    expect(window.localStorage.getItem(BUILDER_GUIDE_PREFERENCE_KEY)).toBe("0");
  });

  it("describes the selected-object next action without inferring completion", () => {
    render(<BuilderGuide hasCapabilities={true} hasRelations={true} hasSelection={true} />);
    fireEvent.click(screen.getByRole("button", { name: "画布提示" }));
    expect(screen.getByText("已选中对象：右侧配置区 会显示对应配置。")).not.toBeNull();
    expect(screen.queryByText("已完成")).toBeNull();
  });

  it("names the next concrete connection in a partial starter graph", () => {
    render(<BuilderGuide hasCapabilities hasRelations progress={{
      hasPerception: true,
      hasReasoning: true,
      hasMemory: true,
      hasActionExecutor: true,
      hasInputTask: true,
      hasInputMemory: true,
      hasMemoryToReasoning: true,
      hasPerceptionToReasoning: true,
      hasReasoningToAction: false,
    }} hasSelection={false} />);
    fireEvent.click(screen.getByRole("button", { name: "画布提示" }));
    expect(screen.getByText("把 Reasoning 的 action 输出连到 Action Executor 的 action 输入。")).not.toBeNull();
    expect(screen.getByText(/设备 observation 由运行时注入/)).not.toBeNull();
  });
});
