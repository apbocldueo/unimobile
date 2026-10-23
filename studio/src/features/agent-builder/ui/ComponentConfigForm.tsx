import { uiText, useUiLocale } from "@/shared/i18n";
import type { JsonValue } from "@/shared/lib";
import { isRecord } from "@/shared/lib";
import styles from "./agentBuilder.module.css";

type JsonSchema = Record<string, JsonValue>;
type JsonObject = Record<string, JsonValue>;

type ComponentConfigFormProps = {
  schema: JsonSchema;
  value: JsonObject;
  onChange: (value: JsonObject) => void;
};

/** Return the JSON object that describes schema properties, or an empty object. */
function schemaProperties(schema: JsonSchema): JsonObject {
  return isRecord(schema.properties) ? schema.properties as JsonObject : {};
}

/** Pick the first supported scalar type from a JSON Schema type declaration. */
function scalarType(schema: JsonSchema): "string" | "integer" | "number" | "boolean" | null {
  const types = Array.isArray(schema.type) ? schema.type : [schema.type];
  for (const type of types) {
    if (type === "string" || type === "integer" || type === "number" || type === "boolean") return type;
  }
  return null;
}

/** Make an underscored Catalog property readable without inventing a new field identity. */
function propertyLabel(name: string, schema: JsonSchema): string {
  if (typeof schema.title === "string" && schema.title.trim()) return schema.title;
  return name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** Convert a JSON scalar into a stable select value. */
function optionToken(value: JsonValue): string {
  return JSON.stringify(value);
}

/** Render one Catalog-declared scalar property and preserve omitted defaults. */
function ConfigProperty({
  name,
  schema,
  value,
  onChange,
}: {
  name: string;
  schema: JsonSchema;
  value: JsonObject;
  onChange: (value: JsonObject) => void;
}) {
  useUiLocale();
  const type = scalarType(schema);
  const hasValue = Object.prototype.hasOwnProperty.call(value, name);
  const current = hasValue ? value[name] : schema.default;
  const label = propertyLabel(name, schema);
  const update = (next: JsonValue | undefined) => {
    const nextValue = { ...value };
    if (next === undefined) delete nextValue[name];
    else nextValue[name] = next;
    onChange(nextValue);
  };
  const enumValues = Array.isArray(schema.enum) ? schema.enum : null;
  if (enumValues) {
    const selected = current === undefined ? "__unset__" : optionToken(current);
    return (
      <div className={styles.formProperty}>
        <label htmlFor={`component-config-${name}`}>{label}</label>
        <select
          id={`component-config-${name}`}
          aria-label={`Config ${name}`}
          className={styles.select}
          value={selected}
          onChange={(event) => {
            if (event.target.value === "__unset__") update(undefined);
            else {
              const selectedValue = enumValues.find((item) => optionToken(item) === event.target.value);
              if (selectedValue !== undefined) update(selectedValue);
            }
          }}
        >
          <option value="__unset__">{uiText("未设置")}{schema.default !== undefined ? uiText("（使用默认值）") : ""}</option>
          {enumValues.map((item) => <option key={optionToken(item)} value={optionToken(item)}>{String(item)}</option>)}
        </select>
        {!hasValue && schema.default !== undefined ? <small className={styles.formHint}>{uiText("默认值：")}{String(schema.default)}</small> : null}
      </div>
    );
  }
  if (type === "boolean") {
    return (
      <label className={styles.formCheckbox}>
        <input
          type="checkbox"
          aria-label={`Config ${name}`}
          checked={current === true}
          onChange={(event) => update(event.target.checked)}
        />
        <span>{label}</span>
        {!hasValue && schema.default !== undefined ? <small className={styles.formHint}>{uiText("默认值：")}{String(schema.default)}</small> : null}
      </label>
    );
  }
  if (type === "string" || type === "integer" || type === "number") {
    const numeric = type === "integer" || type === "number";
    const inputValue = current === undefined || current === null ? "" : String(current);
    return (
      <div className={styles.formProperty}>
        <label htmlFor={`component-config-${name}`}>{label}</label>
        <input
          id={`component-config-${name}`}
          aria-label={`Config ${name}`}
          className={styles.input}
          type={numeric ? "number" : "text"}
          step={type === "integer" ? 1 : "any"}
          min={typeof schema.minimum === "number" ? schema.minimum : undefined}
          max={typeof schema.maximum === "number" ? schema.maximum : undefined}
          value={inputValue}
          onChange={(event) => {
            if (!event.target.value) {
              update(undefined);
              return;
            }
            if (!numeric) {
              update(event.target.value);
              return;
            }
            const parsed = type === "integer" ? Number.parseInt(event.target.value, 10) : Number(event.target.value);
            if (Number.isFinite(parsed)) update(parsed);
          }}
        />
        {!hasValue && schema.default !== undefined ? <small className={styles.formHint}>{uiText("默认值：")}{String(schema.default)}</small> : null}
      </div>
    );
  }
  return (
    <p className={styles.formHint}>
      {label} {" "}{uiText("使用数组或嵌套对象，请在下方“高级 JSON 配置”中编辑。")}</p>
  );
}

/** Render the Catalog-backed component form while leaving complex JSON to the advanced editor. */
export function ComponentConfigForm({ schema, value, onChange }: ComponentConfigFormProps) {
  useUiLocale();
  const properties = Object.entries(schemaProperties(schema));
  if (!properties.length) return <p className={styles.formHint}>{uiText("这个组件没有额外参数。")}</p>;
  return (
    <div className={styles.componentConfigForm} aria-label={uiText("组件参数表单")}>
      <p className={styles.formHint}>{uiText("未填写的字段使用组件默认值（如果 Catalog 提供了默认值）。")}</p>
      {properties.map(([name, property]) => (
        <ConfigProperty
          key={name}
          name={name}
          schema={isRecord(property) ? property as JsonSchema : {}}
          value={value}
          onChange={onChange}
        />
      ))}
    </div>
  );
}
