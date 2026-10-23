import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  IconArchive,
  IconBadgeCheck,
  IconHelpCircle,
  IconHistory,
} from "@/components/icons/StudioIcons";
import { StudioModuleAside } from "./StudioModuleAside";

const ICON = 18;
const STROKE = 1.75;

/** Render one route-owned Benchmark navigation row. */
function NavRow({
  to,
  label,
  icon,
  end = false,
  activePrefix,
}: {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
  activePrefix?: string;
}) {
  const pathname = useLocation().pathname;
  const active =
    (end ? pathname === to : pathname === to || pathname.startsWith(`${to}/`))
    || (activePrefix !== undefined && pathname.startsWith(activePrefix));
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className="block rounded-xl no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)]"
    >
      <div
        className={[
          "group relative flex items-center gap-3 rounded-xl px-3 py-3.5 text-[15px] font-semibold transition",
          active
            ? "bg-[var(--zx-primary)] text-white shadow-[0_12px_32px_rgba(22,93,255,0.28)]"
            : "text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-nav-hover-bg)]",
        ].join(" ")}
      >
        <span
          aria-hidden
          className={[
            "flex h-9 w-9 items-center justify-center rounded-lg",
            active ? "bg-white/15" : "bg-[var(--zx-nav-icon-bg)]",
          ].join(" ")}
        >
          {icon}
        </span>
        {label}
      </div>
    </Link>
  );
}

/** Navigate the Stage 5 Benchmark Catalog, Authoring, Composer, and History. */
export function BenchmarkModuleSidebar() {
  return (
    <StudioModuleAside title="试车场" subtitle="Catalog · Authoring · Experiments">
      <section aria-label="Benchmark 入口" className="flex flex-col gap-2">
        <NavRow
          to="/benchmarks"
          label="Benchmark Catalog"
          icon={<IconArchive size={ICON} strokeWidth={STROKE} aria-hidden />}
        />
        <NavRow
          to="/benchmark-authoring"
          activePrefix="/benchmark-drafts"
          label="Benchmark Authoring"
          icon={<IconBadgeCheck size={ICON} strokeWidth={STROKE} aria-hidden />}
        />
        <NavRow
          to="/experiments/new"
          label="Experiment Composer"
          icon={<IconBadgeCheck size={ICON} strokeWidth={STROKE} aria-hidden />}
        />
        <NavRow
          to="/experiments"
          end
          label="Experiment History"
          icon={<IconHistory size={ICON} strokeWidth={STROKE} aria-hidden />}
        />
      </section>
      <div
        className="h-px shrink-0 bg-[var(--zx-divider-ui)]"
        role="separator"
        aria-hidden
      />
      <NavRow
        to="/help"
        label="帮助中心"
        icon={<IconHelpCircle size={ICON} strokeWidth={STROKE} aria-hidden />}
      />
    </StudioModuleAside>
  );
}
