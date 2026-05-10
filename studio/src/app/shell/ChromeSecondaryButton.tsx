import type { ReactNode } from "react";

type ChromeSecondaryButtonProps = {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  title?: string;
  className?: string;
};

/** 次要操作：深灰底 + 浅灰字，8px 圆角；禁用 #444、字 50% 透明度、无 hover。 */
export function ChromeSecondaryButton({
  children,
  disabled,
  onClick,
  title,
  className = "",
}: ChromeSecondaryButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onClick}
      className={[
        "rounded-lg px-4 py-2.5 text-[13px] font-semibold tracking-tight outline-none transition-[background-color,color,filter]",
        "focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-panel)]",
        disabled
          ? "cursor-not-allowed border-2 border-transparent"
          : "cursor-pointer border-2 border-transparent active:scale-[0.98] active:brightness-[0.94]",
        className,
      ].join(" ")}
      style={
        disabled
          ? {
              backgroundColor: "var(--zx-disabled-bg)",
              color: "rgba(255, 255, 255, var(--zx-disabled-text-opacity))",
            }
          : {
              backgroundColor: "var(--zx-secondary-btn-bg)",
              color: "var(--zx-secondary-btn-text)",
            }
      }
      onMouseEnter={(e) => {
        if (disabled) return;
        e.currentTarget.style.backgroundColor = "var(--zx-secondary-btn-bg-hover)";
        e.currentTarget.style.color = "var(--zx-secondary-btn-text-hover)";
      }}
      onMouseLeave={(e) => {
        if (disabled) return;
        e.currentTarget.style.backgroundColor = "var(--zx-secondary-btn-bg)";
        e.currentTarget.style.color = "var(--zx-secondary-btn-text)";
      }}
    >
      {children}
    </button>
  );
}
