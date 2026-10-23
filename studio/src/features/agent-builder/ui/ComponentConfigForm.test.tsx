import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JsonValue } from "@/shared/lib";
import { ComponentConfigForm } from "./ComponentConfigForm";

describe("ComponentConfigForm", () => {
  it("renders Catalog scalar types and writes typed values", () => {
    let value: Record<string, JsonValue> = { retries: 2, enabled: false, preset: "fast" };
    const view = render(
      <ComponentConfigForm
        schema={{
          type: "object",
          properties: {
            retries: { type: "integer", minimum: 0, default: 3 },
            enabled: { type: "boolean", default: true },
            preset: { type: "string", enum: ["fast", "safe"] },
          },
        }}
        value={value}
        onChange={(next) => { value = next; view.rerender(
          <ComponentConfigForm
            schema={{
              type: "object",
              properties: {
                retries: { type: "integer", minimum: 0, default: 3 },
                enabled: { type: "boolean", default: true },
                preset: { type: "string", enum: ["fast", "safe"] },
              },
            }}
            value={value}
            onChange={(updated) => { value = updated; }}
          />,
        ); }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Config retries"), { target: { value: "4" } });
    expect(value.retries).toBe(4);
    fireEvent.click(screen.getByLabelText("Config enabled"));
    expect(value.enabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Config preset"), { target: { value: JSON.stringify("safe") } });
    expect(value.preset).toBe("safe");
  });

  it("points complex values to the advanced JSON editor", () => {
    render(
      <ComponentConfigForm
        schema={{ type: "object", properties: { steps: { type: "array", items: { type: "string" } } } }}
        value={{}}
        onChange={() => undefined}
      />,
    );
    expect(screen.getByText(/数组或嵌套对象/)).not.toBeNull();
  });
});
