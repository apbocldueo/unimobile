import {
  IconArchive,
  IconBadgeCheck,
  IconBrain,
  IconEye,
  IconLayers,
  IconMap,
  type StudioIconComponent,
} from "./StudioIcons";

const SLOT_ICON_MAP: Record<string, StudioIconComponent> = {
  perception: IconEye,
  reasoning: IconBrain,
  memory: IconArchive,
  planner: IconMap,
  verifier: IconBadgeCheck,
};

type SlotGlyphProps = {
  slotId: string;
  className?: string;
  /** 与导航统一默认 18px */
  size?: number;
  /** 主色 / 正文 / 标题白 */
  tone?: "primary" | "muted" | "title";
};

/** 槽位线性图标：线宽统一，尺寸与导航对齐。 */
export function SlotGlyph({ slotId, className, size = 18, tone = "primary" }: SlotGlyphProps) {
  const Icon = SLOT_ICON_MAP[slotId] ?? IconLayers;
  const color =
    tone === "primary"
      ? "var(--zx-primary)"
      : tone === "title"
        ? "var(--zx-text-title)"
        : "var(--zx-text-muted)";

  return (
    <Icon
      aria-hidden
      size={size}
      strokeWidth={1.75}
      className={className}
      style={{ color }}
    />
  );
}
