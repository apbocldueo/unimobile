import { Link, useLocation } from "react-router-dom";
import {
  IconBot,
  IconFolder,
  IconHistory,
  IconLineChart,
  IconSettings,
} from "@/components/icons/StudioIcons";
import {
  resolveStudioRouteContext,
  STUDIO_GLOBAL_DESTINATIONS,
  type StudioGlobalDestination,
} from "@/app/navigation/studioNavigation";

const ICON_SIZE = 16;
const ICON_STROKE = 1.8;

/** Render the semantic icon assigned to one stable product destination. */
function DestinationIcon({ destination }: { destination: StudioGlobalDestination }) {
  const props = { size: ICON_SIZE, strokeWidth: ICON_STROKE, "aria-hidden": true as const };
  if (destination.icon === "experiments") return <IconLineChart {...props} />;
  if (destination.icon === "runs") return <IconHistory {...props} />;
  if (destination.icon === "settings") return <IconSettings {...props} />;
  if (destination.icon === "agents") return <IconFolder {...props} />;
  return <IconBot {...props} />;
}

/** Render the global object-and-lifecycle navigation shared by all Studio pages. */
export function TopActionBar() {
  const location = useLocation();
  const current = resolveStudioRouteContext(location.pathname).destination;
  return (
    <header
      className="fixed inset-x-0 top-0 z-[100] flex h-[56px] items-center border-b border-[color:var(--zx-divider-ui)] px-5 font-sans shadow-[var(--zx-shadow-chrome)]"
      style={{ backgroundColor: "var(--studio-chrome-bg)" }}
    >
      <Link
        to="/"
        aria-label="ZhiXing Studio 首页"
        className="mr-8 flex shrink-0 items-center gap-2 rounded-lg text-[color:var(--zx-text-title)] no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)]"
      >
        <span className="text-[color:var(--zx-primary)]" aria-hidden>
          <IconBot size={20} strokeWidth={ICON_STROKE} />
        </span>
        <strong className="text-[16px] tracking-tight">ZhiXing Studio</strong>
      </Link>
      <nav aria-label="全局导航" className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {STUDIO_GLOBAL_DESTINATIONS.map((destination) => {
          const active = destination.id === current;
          return (
            <Link
              key={destination.id}
              to={destination.path}
              aria-current={active ? "page" : undefined}
              className={[
                "relative flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-[13px] no-underline outline-none transition-colors",
                "focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2",
                active
                  ? "bg-[var(--zx-primary-soft)] font-semibold text-[color:var(--zx-text-title)] after:absolute after:inset-x-3 after:-bottom-[8px] after:h-[2px] after:bg-[var(--zx-primary)]"
                  : "font-medium text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-text-title)]",
              ].join(" ")}
            >
              <DestinationIcon destination={destination} />
              <span>{destination.label}</span>
            </Link>
          );
        })}
      </nav>
      <Link
        to="/help"
        className="ml-4 shrink-0 rounded-lg px-3 py-2 text-[12px] font-medium text-[color:var(--zx-text-muted)] no-underline outline-none hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-text-title)] focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)]"
      >
        帮助
      </Link>
    </header>
  );
}
