import { NavLink } from "react-router-dom";

/** Switch between independent Run and Experiment histories without merging resources. */
export function RunsTypeTabs({ active }: { active: "ordinary" | "experiment" }) {
  const tab = (selected: boolean) => [
    "rounded-lg px-3 py-2 text-[11px] font-semibold no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)]",
    selected
      ? "bg-[var(--zx-primary-soft)] text-[color:var(--zx-text-title)]"
      : "text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-nav-hover-bg)]",
  ].join(" ");
  return (
    <nav aria-label="运行记录类型" className="flex shrink-0 gap-1 border-b border-[var(--zx-divider-ui)] px-6 py-2">
      <NavLink to="/history" aria-current={active === "ordinary" ? "page" : undefined} className={tab(active === "ordinary")}>普通 Agent Runs</NavLink>
      <NavLink to="/experiments" aria-current={active === "experiment" ? "page" : undefined} className={tab(active === "experiment")}>Benchmark Experiments</NavLink>
    </nav>
  );
}
