import type { ReactNode } from "react";

type ChromePrimaryButtonProps = {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  /** 禁用时提示原因 */
  title?: string;
  className?: string;
};

/** 主操作：主色底 + 白字 + 8px 圆角；hover 略加深、active 瞬时变深；禁用 #444、字 50%。 */
export function ChromePrimaryButton({ children, disabled, onClick, title, className = "" }: ChromePrimaryButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onClick}
      className={[
        "rounded-lg px-4 py-2.5 text-[13px] font-semibold tracking-tight outline-none transition-[filter,opacity,background-color]",
        "focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-panel)]",
        disabled
          ? "cursor-not-allowed"
          : "cursor-pointer hover:brightness-[0.94] active:scale-[0.98] active:brightness-[0.86]",
        className,
      ].join(" ")}
      style={
        disabled
          ? {
              backgroundColor: "var(--zx-disabled-bg)",
              color: "rgba(255, 255, 255, var(--zx-disabled-text-opacity))",
            }
          : {
              backgroundColor: "var(--zx-primary)",
              color: "#ffffff",
              boxShadow: "0 2px 12px rgba(90, 174, 253, 0.28)",
            }
      }
    >
      {children}
    </button>
  );
}
