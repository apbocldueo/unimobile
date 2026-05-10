import {
  buildParamValueErrors,
  getPluginParamGroups,
  type ParamFieldDef,
} from "@/domain/agent/pluginParamUi";

function ParamControl({
  field,
  value,
  error,
  onChange,
  appearance,
}: {
  field: ParamFieldDef;
  value: string;
  error?: string;
  onChange: (v: string) => void;
  appearance: "default" | "inspector";
}) {
  if (appearance === "inspector") {
    const cls = ["flow-inspector-control", error ? "flow-inspector-control--error" : ""].filter(Boolean).join(" ");
    if (field.kind === "select") {
      return (
        <div className="flex flex-col">
          <select className={cls} value={value} onChange={(e) => onChange(e.target.value)} onPointerDown={(e) => e.stopPropagation()}>
            {field.options.map((o) => (
              <option key={o.value} value={o.value} className="bg-[#2a2a2a] text-[#eeeeee]">
                {o.label}
              </option>
            ))}
          </select>
          {error ? <p className="flow-inspector-help flow-inspector-help--error">{error}</p> : null}
        </div>
      );
    }
    if (field.kind === "number") {
      return (
        <div className="flex flex-col">
          <input
            type="number"
            className={cls}
            value={value}
            min={field.min}
            max={field.max}
            onChange={(e) => onChange(e.target.value)}
            onPointerDown={(e) => e.stopPropagation()}
          />
          {error ? <p className="flow-inspector-help flow-inspector-help--error">{error}</p> : null}
        </div>
      );
    }
    return (
      <div className="flex flex-col">
        <input
          type="text"
          className={cls}
          value={value}
          placeholder={field.placeholder}
          onChange={(e) => onChange(e.target.value)}
          onPointerDown={(e) => e.stopPropagation()}
        />
        {error ? <p className="flow-inspector-help flow-inspector-help--error">{error}</p> : null}
      </div>
    );
  }

  const baseCls =
    "flow-toolbar-input w-full font-sans text-[12px] text-[color:var(--zx-text-title)] outline-none focus:border-[color:var(--zx-primary-border)]";

  if (field.kind === "select") {
    return (
      <div className="flex flex-col gap-1">
        <select className={baseCls} value={value} onChange={(e) => onChange(e.target.value)} onPointerDown={(e) => e.stopPropagation()}>
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {error ? <p className="text-[11px] text-red-300">{error}</p> : null}
      </div>
    );
  }
  if (field.kind === "number") {
    return (
      <div className="flex flex-col gap-1">
        <input
          type="number"
          className={baseCls}
          value={value}
          min={field.min}
          max={field.max}
          onChange={(e) => onChange(e.target.value)}
          onPointerDown={(e) => e.stopPropagation()}
        />
        {error ? <p className="text-[11px] text-red-300">{error}</p> : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <input
        type="text"
        className={baseCls}
        value={value}
        placeholder={field.placeholder}
        onChange={(e) => onChange(e.target.value)}
        onPointerDown={(e) => e.stopPropagation()}
      />
      {error ? <p className="text-[11px] text-red-300">{error}</p> : null}
    </div>
  );
}

export type PluginParamFormProps = {
  pluginId: string;
  values: Record<string, string>;
  onChange: (paramId: string, value: string) => void;
  /** 流程检查器：与 flow-inspector-* 样式一致 */
  appearance?: "default" | "inspector";
};

/** 与兵工厂槽位面板共用参数定义（pluginParamUi / 远程 paramCatalog）。 */
export function PluginParamForm({ pluginId, values, onChange, appearance = "default" }: PluginParamFormProps) {
  const groups = getPluginParamGroups(pluginId);
  const errors = buildParamValueErrors(pluginId, values);
  if (!groups.length) {
    return (
      <p className={appearance === "inspector" ? "flow-inspector-muted-block" : "text-[12px] text-[color:var(--zx-text-muted)]"}>
        该算法暂无可编辑参数定义。
      </p>
    );
  }
  const isInsp = appearance === "inspector";
  return (
    <div className={isInsp ? "flex flex-col gap-4" : "flex flex-col gap-4"}>
      {groups.map((g, gi) => (
        <section key={g.id}>
          <div
            className={
              isInsp
                ? ["flow-inspector-group-title", gi === 0 ? "flow-inspector-group-title--flush" : ""].join(" ")
                : "mb-2 text-[11px] font-semibold uppercase tracking-wide text-[color:var(--zx-text-muted)]"
            }
          >
            {g.title}
            {g.tier === "advanced" ? <span className="ml-2 font-normal opacity-80">（高级）</span> : null}
          </div>
          <div className={isInsp ? "flex flex-col gap-4" : "flex flex-col gap-3"}>
            {g.fields.map((f) => (
              <div key={f.id}>
                {isInsp ? (
                  <div className="flow-inspector-field-label">
                    <label htmlFor={`flow-param-${pluginId}-${f.id}`}>{f.label}</label>
                    {f.hint ? (
                      <span className="flow-inspector-field-hint-icon" title={f.hint}>
                        ?
                      </span>
                    ) : null}
                  </div>
                ) : (
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-[color:var(--zx-text-muted)]" htmlFor={`flow-param-${pluginId}-${f.id}`}>
                      {f.label}
                    </label>
                    {f.hint ? <p className="mb-1 text-[10px] leading-snug text-[color:var(--zx-text-muted)]">{f.hint}</p> : null}
                  </div>
                )}
                <ParamControl field={f} value={values[f.id] ?? ""} error={errors[f.id]} onChange={(v) => onChange(f.id, v)} appearance={appearance} />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
