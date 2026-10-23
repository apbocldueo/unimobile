import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { helpTopics, type HelpTopicId } from "../model/helpTopics";
import { documentationLink } from "../model/documentationLinks";
import { HelpTopics } from "./HelpTopics";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("task-oriented bilingual Help", () => {
  it.each(Object.keys(helpTopics) as HelpTopicId[])("preserves topic %s through language changes without runtime requests", (topic) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<MemoryRouter initialEntries={[`/help?topic=${topic}&lang=en`]}><HelpTopics /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: helpTopics[topic].en.title })).not.toBeNull();
    fireEvent.change(screen.getByLabelText("Help language"), { target: { value: "zh-CN" } });
    expect(screen.getByRole("heading", { name: helpTopics[topic]["zh-CN"].title })).not.toBeNull();
    expect(screen.getAllByRole("listitem")).toHaveLength(helpTopics[topic].en.steps.length);
    const article = documentationLink(topic, "zh-CN");
    const link = screen.getByRole("link", { name: `${article.label} ↗` });
    expect(link.getAttribute("href")).toBe(article.href);
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(screen.queryByText(/没有部署新的站点页面/)).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("defaults untrusted topic and language values to the safe Chinese start topic", () => {
    render(<MemoryRouter initialEntries={["/help?topic=https://evil.invalid&lang=unknown"]}><HelpTopics /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: helpTopics.start["zh-CN"].title })).not.toBeNull();
    expect(screen.getByLabelText("Help language").getAttribute("aria-label")).toBe("Help language");
    for (const link of screen.getAllByRole("link")) expect(link.getAttribute("href")).not.toContain("evil.invalid");
    fireEvent.click(screen.getByRole("button", { name: helpTopics.model["zh-CN"].title }));
    expect(screen.getByRole("heading", { name: helpTopics.model["zh-CN"].title })).not.toBeNull();
  });
});
