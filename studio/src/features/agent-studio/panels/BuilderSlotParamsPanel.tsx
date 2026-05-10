import { useCallback, useEffect, useMemo, useState } from "react";
import { IconHelpCircle } from "@/components/icons/StudioIcons";
import {
  buildParamValueErrors,
  getDefaultSlotParamValues,
  getPluginParamGroups,
  validateParamField,
  type ParamFieldDef,
} from "@/domain/agent/pluginParamUi";
import { useAgentBuilderStore } from "@/stores/agentBuilderStore";
import { ChromeSecondaryButton } from "@/app/shell/ChromeSecondaryButton";

const ERR_COLOR = "#ff8a8a";
const ERR_BORDER = "rgba(255, 130, 130, 0.75)";
const LABEL_COLOR = "rgba(185,193,208,0.85)";

function PanelParamField({
  field,
  value,
  error,
  onChange,
  onBlurCommit,
}: {
  field: ParamFieldDef;
  value: string;
  error?: string;
  onChange: (v: string) => void;
  onBlurCommit: () => void;
}) {
  const borderColor = error ? ERR_BORDER : undefined;
  const baseStyle = { color: "#ffffff", ...(borderColor ? { borderColor } : {}) } as const;
  const cls =
    "zx-control w-full px-2.5 py-2 text-[12px] outline-none transition-[border-color,box-shadow,background-color]";

  if (field.kind === "select") {
    return (
      <div className="flex flex-col gap-1">
        <select className={cls} style={baseStyle} value={value} onChange={(e) => onChange(e.target.value)} onBlur={onBlurCommit}>
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {error ? <p className="text-[11px]" style={{ color: ERR_COLOR }}>{error}</p> : null}
      </div>
    );
  }
  if (field.kind === "number") {
    return (
      <div className="flex flex-col gap-1">
        <input
          type="number"
          className={cls}
          style={baseStyle}
          value={value}
          min={field.min}
          max={field.max}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlurCommit}
        />
        {error ? <p className="text-[11px]" style={{ color: ERR_COLOR }}>{error}</p> : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <input
        type="text"
        className={cls}
        style={baseStyle}
        value={value}
        placeholder={field.placeholder}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlurCommit}
      />
      {error ? <p className="text-[11px]" style={{ color: ERR_COLOR }}>{error}</p> : null}
    </div>
  );
}

type Props = { slotId: string };

/**
 * 兵工厂右栏：当前槽位全部超参数（与画布卡片 store 双向同步）。
 */
export function BuilderSlotParamsPanel({ slotId }: Props) {
  const assignment = useAgentBuilderStore((s) => s.assignments[slotId]);
  const slotParamValues = useAgentBuilderStore((s) => s.slotParamValues[slotId]);
  const setSlotParamValue = useAgentBuilderStore((s) => s.setSlotParamValue);
  const openPluginShowcase = useAgentBuilderStore((s) => s.openPluginShowcase);

  const pluginId = assignment?.pluginId ?? "";
  const groups = useMemo(() => (pluginId ? getPluginParamGroups(pluginId) : []), [pluginId]);
  const defaults = useMemo(() => (pluginId ? getDefaultSlotParamValues(pluginId) : {}), [pluginId]);
  const merged = useMemo(() => ({ ...defaults, ...(slotParamValues ?? {}) }), [defaults, slotParamValues]);

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const glist = pluginId ? getPluginParamGroups(pluginId) : [];
    const next: Record<string, boolean> = {};
    for (const g of glist) {
      next[g.id] = g.tier !== "advanced";
    }
    setExpanded(next);
  }, [pluginId]);

  const displayErrors = useMemo(() => (pluginId ? buildParamValueErrors(pluginId, merged) : {}), [pluginId, merged]);

  const toggleGroup = useCallback((id: string) => {
    setExpanded((s) => ({ ...s, [id]: !s[id] }));
  }, []);

  if (!assignment || !pluginId) {
    return (
      <p className="text-center text-[12px] leading-relaxed" style={{ color: "rgba(185,193,208,0.45)" }}>
        请先为该组件选择算法
      </p>
    );
  }

  if (groups.length === 0) {
    return (
      <p className="text-[12px] leading-relaxed" style={{ color: LABEL_COLOR }}>
        当前算法暂无可配置超参数项。
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ChromeSecondaryButton className="w-full py-2 text-[12px] font-medium" onClick={() => openPluginShowcase(slotId)}>
        切换算法…
      </ChromeSecondaryButton>

      {groups.map((group, gi) => (
        <div key={group.id}>
          {gi > 0 ? <div className="mb-4 h-px w-full" style={{ backgroundColor: "var(--zx-divider-ui)" }} /> : null}
          <button
            type="button"
            className="studio-aux-hit flex w-full items-center justify-between gap-2 px-1 py-1.5 text-left outline-none"
            onClick={() => toggleGroup(group.id)}
          >
            <span className="text-[13px] font-bold text-white">{group.title}</span>
            <span className="text-[11px] tabular-nums" style={{ color: LABEL_COLOR }}>
              {expanded[group.id] ? "收起" : "展开"}
            </span>
          </button>
          {expanded[group.id] ? (
            <div className="mt-3 flex flex-col gap-3.5">
              {group.fields.map((field) => (
                <div key={field.id} className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[12px]" style={{ color: LABEL_COLOR }}>
                      {field.label}
                    </span>
                    {field.hint ? (
                      <span className="studio-aux-hit inline-flex cursor-help items-center p-0.5 opacity-90" title={field.hint}>
                        <IconHelpCircle size={12} strokeWidth={2} aria-hidden />
                        <span className="sr-only">{field.hint}</span>
                      </span>
                    ) : null}
                  </div>
                  <PanelParamField
                    field={field}
                    value={merged[field.id] ?? ""}
                    error={displayErrors[field.id]}
                    onChange={(v) => setSlotParamValue(slotId, field.id, v)}
                    onBlurCommit={() => {
                      validateParamField(field, merged[field.id] ?? "");
                    }}
                  />
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
