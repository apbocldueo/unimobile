import { useCallback, useEffect, useState } from "react";
import { useModuleNavSwitch } from "@/app/shell/ModuleNavSwitchContext";
import { IconBot, IconLineChart } from "@/components/icons/StudioIcons";
import type { StudioHomeLaunchCardIcon, StudioHomeLaunchItem } from "./studioHomeLaunchConfig";
import { STUDIO_HOME_LAUNCH_SECTIONS } from "./studioHomeLaunchConfig";
import { StudioHomeArmoryEntryModal } from "./StudioHomeArmoryEntryModal";
import { StudioHomeLeftSidebar } from "./StudioHomeLeftSidebar";
import { StudioHomeTopNav } from "./StudioHomeTopNav";

function LaunchCardIcon({ kind }: { kind?: StudioHomeLaunchCardIcon }) {
  const p = { size: 26 as const, strokeWidth: 1.85 as const, className: "text-current" as const };
  if (kind === "lineChart") return <IconLineChart {...p} />;
  return <IconBot {...p} />;
}

function LaunchTile({
  label,
  description,
  icon,
  onEnter,
}: {
  label: string;
  description?: string;
  icon?: StudioHomeLaunchCardIcon;
  onEnter: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onEnter}
      className="group flex w-full max-w-sm shrink-0 flex-col items-stretch gap-2 rounded-2xl border px-8 py-10 text-left outline-none transition-[border-color,box-shadow,transform,background-color] focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-4 focus-visible:ring-offset-[var(--zx-app)] hover:-translate-y-0.5 hover:border-[color:var(--zx-primary-border)] hover:shadow-[0_12px_40px_rgba(90,174,253,0.22)] sm:max-w-[280px]"
      style={{
        borderColor: "var(--zx-border-light)",
        backgroundColor: "var(--zx-card)",
        boxShadow: "var(--zx-shadow-soft)",
      }}
    >
      <span className="flex items-center gap-3">
        <span
          aria-hidden
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-black/25 text-[color:var(--zx-primary)] transition-colors group-hover:bg-[color:var(--zx-primary-soft)]"
        >
          <LaunchCardIcon kind={icon} />
        </span>
        <span className="text-[18px] font-semibold tracking-tight text-[color:var(--zx-text-title)]">{label}</span>
      </span>
      {description ? (
        <p className="pl-[3.75rem] text-[13px] leading-relaxed text-[color:var(--zx-text-muted)]">{description}</p>
      ) : null}
    </button>
  );
}

/**
 * 应用开始页：内容由 `studioHomeLaunchConfig.ts` 驱动，便于后续增加区块与其它入口。
 */
export function StudioHomePage() {
  const { switchModule } = useModuleNavSwitch();
  const [gateItem, setGateItem] = useState<StudioHomeLaunchItem | null>(null);

  const closeGate = useCallback(() => setGateItem(null), []);

  useEffect(() => {
    if (!gateItem) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeGate();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [gateItem, closeGate]);

  const onLaunchTileActivate = useCallback(
    (item: StudioHomeLaunchItem) => {
      if (item.gateModal) {
        setGateItem(item);
        return;
      }
      void switchModule(item.to);
    },
    [switchModule],
  );

  return (
    <div
      className="relative flex h-[100dvh] min-h-0 w-full flex-col overflow-hidden bg-[var(--zx-app)] font-sans text-[color:var(--zx-text-body)] antialiased"
      role="main"
      aria-label="开始页"
    >
      <StudioHomeTopNav />
      <div className="flex min-h-0 flex-1 flex-col pt-14">
        <div className="flex min-h-0 min-w-0 flex-1">
          <StudioHomeLeftSidebar />
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            <div
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_85%_55%_at_50%_-18%,rgba(64,150,255,0.14),transparent_55%)]"
              aria-hidden
            />
            <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto overflow-x-hidden px-6 pb-12 pt-10">
        <div className="flex w-full max-w-3xl flex-col items-center gap-10">
          <header className="text-center">
            <h1 className="text-[18px] font-semibold tracking-tight text-[color:var(--zx-text-title)]">选择要进入的模块</h1>
            <p className="mt-2 max-w-md text-[13px] leading-relaxed text-[color:var(--zx-text-muted)]">点击下方卡片进入对应工作区</p>
          </header>

          <div className="flex w-full flex-col items-center gap-12">
            {STUDIO_HOME_LAUNCH_SECTIONS.map((section) => (
              <section
                key={section.id}
                className="flex w-full flex-col items-center gap-4"
                aria-labelledby={section.title ? `home-section-${section.id}` : undefined}
              >
                {section.title ? (
                  <h2
                    id={`home-section-${section.id}`}
                    className="text-[12px] font-semibold uppercase tracking-wider text-[color:var(--zx-text-muted)]"
                  >
                    {section.title}
                  </h2>
                ) : null}
                <div className="flex w-full flex-col items-center justify-center gap-6 sm:flex-row sm:flex-wrap">
                  {section.items.map((item) => (
                    <LaunchTile
                      key={item.id}
                      label={item.label}
                      description={item.description}
                      icon={item.icon}
                      onEnter={() => onLaunchTileActivate(item)}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
            </div>
          </div>
        </div>
      </div>

      {gateItem?.gateModal?.kind === "armory-flow-picker" ? <StudioHomeArmoryEntryModal onClose={closeGate} /> : null}
    </div>
  );
}
