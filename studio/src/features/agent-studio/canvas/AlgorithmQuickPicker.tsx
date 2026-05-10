import { useCallback, useEffect, useRef, useState } from "react";
import type { SlotAlgorithmOption } from "@/domain/agent/slotAlgorithmOptions";

type AlgorithmQuickPickerProps = {
  /** 仅本槽位在 ZhiXing 注册表中的插件；与槽位无关的全局列表禁止传入。 */
  options: SlotAlgorithmOption[];
  value: string;
  onPick: (pluginId: string) => void;
  placeholder: string;
  disabled?: boolean;
  /** 空槽主 CTA：主色、8px 圆角 */
  variant?: "default" | "cta";
  /** 流程检查器内：与 #242424 卡片体系一致的控件样式 */
  appearance?: "default" | "inspector";
};

/**
 * 槽位内算法快选：选项必须由父组件按 ``slotId`` 从后端注册表裁剪后传入。
 */
export function AlgorithmQuickPicker({
  options,
  value,
  onPick,
  placeholder,
  disabled,
  variant = "default",
  appearance = "default",
}: AlgorithmQuickPickerProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, close]);

  const label = options.find((p) => p.id === value)?.title ?? (value ? value : placeholder);

  const isCta = variant === "cta" && !value;
  const isInspector = appearance === "inspector";

  const defaultBtn = {
    color: "#ffffff",
    borderColor: "var(--zx-control-border)",
    backgroundColor: "var(--zx-control-bg)",
    boxShadow: open ? "0 0 0 1px rgba(22,93,255,0.32)" : undefined,
  } as const;

  const ctaBtn = {
    color: "#ffffff",
    borderColor: "transparent",
    boxShadow: open ? "0 0 0 1px rgba(22,93,255,0.45), 0 4px 14px rgba(0,0,0,0.28)" : "0 2px 10px rgba(0,0,0,0.22)",
  } as const;

  if (options.length === 0) {
    return null;
  }

  if (isInspector) {
    return (
      <div ref={rootRef} data-slot-interactive className="relative w-full">
        <button
          type="button"
          disabled={disabled}
          className={[
            "nodrag w-full outline-none transition-[transform,filter] focus-visible:ring-2 focus-visible:ring-[#4096ff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#242424] disabled:cursor-not-allowed disabled:opacity-45",
            isCta ? "flow-inspector-algo-trigger" : "flow-inspector-algo-trigger flow-inspector-algo-trigger--secondary",
          ].join(" ")}
          aria-expanded={open}
          aria-haspopup="listbox"
          onClick={(e) => {
            e.stopPropagation();
            if (!disabled) setOpen((o) => !o);
          }}
        >
          {value ? label : placeholder}
        </button>
        {open && !disabled ? (
          <ul className="flow-inspector-algo-list absolute left-0 right-0 z-[60]" role="listbox">
            {options.map((p) => (
              <li key={p.id} role="none">
                <button
                  type="button"
                  className={[
                    "nodrag flow-inspector-algo-option",
                    p.id === value ? "flow-inspector-algo-option--active" : "",
                  ].join(" ")}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (p.id === value) {
                      close();
                      return;
                    }
                    onPick(p.id);
                    close();
                  }}
                >
                  <span className="font-mono text-[12px] text-[#e8ecf4]">{p.id}</span>
                  <span className="mt-1 block text-[12px] font-normal text-[#a0a0a0]">{p.title}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      data-slot-interactive
      className={`relative w-full ${isCta ? "max-w-[220px]" : "max-w-[240px]"}`}
    >
      <button
        type="button"
        disabled={disabled}
        className={[
          "nodrag flex w-full items-center justify-center rounded-lg border-2 px-3 py-2.5 text-center text-[13px] outline-none transition-[border-color,box-shadow,transform,filter,background-color] focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[#1e1e1e] enabled:active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50",
          isCta ? "bg-[#165dff] font-semibold enabled:hover:bg-[#0d47a1]" : "font-medium",
        ].join(" ")}
        style={isCta ? ctaBtn : defaultBtn}
        aria-expanded={open}
        aria-haspopup="listbox"
        onMouseEnter={(e) => {
          if (disabled || isCta) return;
          e.currentTarget.style.backgroundColor = "var(--zx-control-bg-hover)";
        }}
        onMouseLeave={(e) => {
          if (disabled || isCta) return;
          e.currentTarget.style.backgroundColor = "var(--zx-control-bg)";
        }}
        onClick={(e) => {
          e.stopPropagation();
          if (!disabled) setOpen((o) => !o);
        }}
      >
        {value ? label : placeholder}
      </button>
      {open && !disabled ? (
        <ul
          className="absolute left-0 right-0 z-[60] mt-1 max-h-56 origin-top overflow-auto rounded-lg border-2 py-1"
          style={{
            borderColor: "var(--zx-control-border)",
            backgroundColor: "var(--zx-control-bg)",
            boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
          }}
          role="listbox"
        >
          {options.map((p) => (
            <li key={p.id} role="none">
              <button
                type="button"
                className="nodrag w-full px-3 py-2.5 text-center text-[13px] font-medium outline-none transition-colors"
                style={{
                  color: p.id === value ? "#ffffff" : "var(--zx-text-title)",
                  backgroundColor: p.id === value ? "var(--zx-primary)" : "transparent",
                }}
                onMouseEnter={(e) => {
                  if (p.id === value) return;
                  e.currentTarget.style.backgroundColor = "var(--zx-primary-soft-strong)";
                }}
                onMouseLeave={(e) => {
                  if (p.id === value) {
                    e.currentTarget.style.backgroundColor = "var(--zx-primary)";
                    return;
                  }
                  e.currentTarget.style.backgroundColor = "transparent";
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (p.id === value) {
                    close();
                    return;
                  }
                  onPick(p.id);
                  close();
                }}
              >
                {p.id}
                <span className="mt-0.5 block text-[11px] font-normal opacity-80">{p.title}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
