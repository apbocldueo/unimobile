import { uiText, useUiLocale } from "@/shared/i18n";
import { useMemo, useState } from "react";
import type {
  ComponentCatalog,
  ComponentCatalogItem,
  ComponentDependencySlot,
} from "@/entities/component-catalog";
import { isRecord, type JsonValue } from "@/shared/lib";
import styles from "./agentBuilder.module.css";

type JsonObject = Record<string, JsonValue>;

type LlmDependencyFormProps = {
  slot: ComponentDependencySlot;
  catalog: ComponentCatalog | null;
  value: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
};

/** Return the object-valued portion of a JSON value without trusting its shape. */
function objectValue(value: JsonValue | undefined): JsonObject {
  return isRecord(value) ? value as JsonObject : {};
}

/** Return the dependency-only providers accepted by one Catalog dependency slot. */
function availableProviders(
  slot: ComponentDependencySlot,
  catalog: ComponentCatalog | null,
): ComponentCatalogItem[] {
  return (catalog?.components ?? []).filter((item) =>
    item.availability.available &&
    item.placement === "dependency_only" &&
    (!slot.acceptedNamespaces.length || slot.acceptedNamespaces.includes(item.namespace)) &&
    (!slot.acceptedCategories.length || slot.acceptedCategories.includes(item.category)),
  );
}

/** Build the stable Catalog identity used by a dependency provider selector. */
function providerIdentity(provider: Pick<ComponentCatalogItem, "namespace" | "name" | "version">): string {
  return `${provider.namespace}:${provider.name}@${provider.version}`;
}

/** Return true when a saved dependency points at a specific Catalog provider. */
function dependencyMatches(value: JsonObject, provider: ComponentCatalogItem): boolean {
  return value.namespace === provider.namespace && value.name === provider.name && value.version === provider.version;
}

/** Read a nested SecretRef object while keeping raw values out of the form state. */
function secretRefValue(value: JsonValue | undefined): string {
  const object = objectValue(value);
  return typeof object.secret_ref === "string" ? object.secret_ref : "";
}

/** Turn a provider schema property into a readable label for first-time users. */
function propertyLabel(name: string): string {
  const labels: Record<string, string> = {
    model: uiText("模型 ID"),
    temperature: uiText("温度"),
    max_tokens: uiText("最大输出 Token"),
    request_timeout: uiText("请求超时（秒）"),
    max_retries: uiText("最大重试次数"),
  };
  return labels[name] ?? name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** Pick the first scalar type supported by a provider JSON Schema property. */
function scalarType(schema: JsonObject): "string" | "integer" | "number" | "boolean" | null {
  const types = Array.isArray(schema.type) ? schema.type : [schema.type];
  for (const type of types) {
    if (type === "string" || type === "integer" || type === "number" || type === "boolean") return type;
  }
  return null;
}

/** Render one scalar provider parameter and preserve omitted Catalog defaults.
 * Args: name and schema identify the Catalog property; params is the current
 * provider configuration; onChange receives the updated JSON object.
 */
function ScalarParameter({
  name,
  schema,
  params,
  onChange,
}: {
  name: string;
  schema: JsonObject;
  params: JsonObject;
  onChange: (params: JsonObject) => void;
}) {
  useUiLocale();
  const type = scalarType(schema);
  const hasValue = Object.prototype.hasOwnProperty.call(params, name);
  const current = hasValue ? params[name] : schema.default;
  const label = propertyLabel(name);
  const update = (next: JsonValue | undefined) => {
    const nextParams = { ...params };
    if (next === undefined) delete nextParams[name];
    else nextParams[name] = next;
    onChange(nextParams);
  };
  if (type === "boolean") {
    return (
      <label className={styles.formCheckbox}>
        <input
          type="checkbox"
          aria-label={label}
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
        <label htmlFor={`llm-config-${name}`}>{label}</label>
        <input
          id={`llm-config-${name}`}
          aria-label={label}
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
  return <p className={styles.formHint}>{label} {" "}{uiText("是扩展对象，请在“高级依赖 JSON”中编辑。")}</p>;
}

/** Present a Catalog-backed model dependency without exposing raw credential inputs. */
export function LlmDependencyForm({ slot, catalog, value, onChange }: LlmDependencyFormProps) {
  const uiLocale = useUiLocale();
  const providers = useMemo(() => availableProviders(slot, catalog), [catalog, slot, uiLocale]);
  const dependency = objectValue(value);
  const selectedProvider = providers.find((item) => dependencyMatches(dependency, item));
  const savedIdentity = typeof dependency.namespace === "string" && typeof dependency.name === "string" && typeof dependency.version === "string"
    ? `${dependency.namespace}:${dependency.name}@${dependency.version}`
    : "";
  const [baseUrlMode, setBaseUrlMode] = useState<"url" | "secret_ref">(
    isRecord(dependency.params) && isRecord(dependency.params.base_url) ? "secret_ref" : "url",
  );
  const params = objectValue(dependency.params);
  const providerSchema = selectedProvider?.configSchema;
  const properties = isRecord(providerSchema?.properties) ? providerSchema.properties as JsonObject : {};
  const requiredProperties = Array.isArray(providerSchema?.required) ? providerSchema.required.filter((item): item is string => typeof item === "string") : [];
  const updateParams = (nextParams: JsonObject) => onChange({
    namespace: dependency.namespace,
    name: dependency.name,
    version: dependency.version,
    params: nextParams,
  });

  if (!providers.length) {
    return (
      <div className={styles.dependencyForm} aria-label={uiText("模型依赖")}>
        <strong className={styles.dependencyFormTitle}>{uiText("模型依赖")}</strong>
        <p className={styles.formHint}>{uiText("当前 Catalog 没有可用的模型提供方。请先检查后端组件可用性，或使用高级依赖 JSON。")}</p>
      </div>
    );
  }

  return (
    <div className={styles.dependencyForm} aria-label={uiText("模型依赖")}>
      <strong className={styles.dependencyFormTitle}>{uiText("模型依赖")}</strong>
      <div className={styles.formProperty}>
        <label htmlFor="llm-provider">{uiText("模型提供方")}</label>
        <select
          id="llm-provider"
          aria-label={uiText("模型提供方")}
          className={styles.select}
          value={selectedProvider ? providerIdentity(selectedProvider) : savedIdentity}
          onChange={(event) => {
            const provider = providers.find((item) => providerIdentity(item) === event.target.value);
            if (!provider) return;
            const sameProvider = dependencyMatches(dependency, provider);
            onChange({
              namespace: provider.namespace,
              name: provider.name,
              version: provider.version,
              params: sameProvider ? params : {},
            });
            setBaseUrlMode("url");
          }}
        >
          {!selectedProvider && savedIdentity ? <option value={savedIdentity}>{uiText("当前提供方不可用（")}{savedIdentity}）</option> : <option value="">{uiText("请选择模型提供方")}</option>}
          {providers.map((provider) => <option key={providerIdentity(provider)} value={providerIdentity(provider)}>{provider.display.label} · {provider.version}</option>)}
        </select>
      </div>
      {!selectedProvider ? (
        <p className={styles.formHint}>{uiText("选择提供方后填写模型 ID 和 SecretRef。SecretRef 只引用服务端凭证，不会把 API Key 保存到 Agent 文档。")}</p>
      ) : (
        <>
          {properties.api_key && isRecord(properties.api_key) ? (
            <div className={styles.formProperty}>
              <label htmlFor="llm-api-key-secret-ref">{uiText("API 凭证 SecretRef")}{requiredProperties.includes("api_key") ? uiText("（必填）") : ""}</label>
              <input
                id="llm-api-key-secret-ref"
                aria-label={uiText("API 凭证 SecretRef")}
                className={styles.input}
                type="text"
                autoComplete="off"
                value={secretRefValue(params.api_key)}
                placeholder={uiText("例如 openai_api_key")}
                onChange={(event) => {
                  const secretRef = event.target.value;
                  const nextParams = { ...params };
                  if (secretRef) nextParams.api_key = { secret_ref: secretRef };
                  else delete nextParams.api_key;
                  updateParams(nextParams);
                }}
              />
              <small className={styles.formHint}>{uiText("只填写 SecretRef 名称，不填写密钥本身。")}</small>
            </div>
          ) : null}
          {properties.base_url && isRecord(properties.base_url) ? (
            <div className={styles.formProperty}>
              <label htmlFor="llm-base-url">{uiText("服务地址（可选）")}</label>
              <select
                aria-label={uiText("服务地址类型")}
                className={styles.select}
                value={baseUrlMode}
                onChange={(event) => {
                  const mode = event.target.value as "url" | "secret_ref";
                  setBaseUrlMode(mode);
                  const nextParams = { ...params };
                  delete nextParams.base_url;
                  updateParams(nextParams);
                }}
              >
                <option value="url">{uiText("直接填写 URL")}</option>
                <option value="secret_ref">{uiText("使用 SecretRef")}</option>
              </select>
              <input
                id="llm-base-url"
                aria-label={baseUrlMode === "url" ? uiText("服务地址 URL") : uiText("服务地址 SecretRef")}
                className={styles.input}
                type="text"
                value={baseUrlMode === "secret_ref" ? secretRefValue(params.base_url) : typeof params.base_url === "string" ? params.base_url : ""}
                placeholder={baseUrlMode === "secret_ref" ? uiText("例如 openai_base_url") : "https://api.example.com/v1"}
                onChange={(event) => {
                  const nextParams = { ...params };
                  if (!event.target.value) delete nextParams.base_url;
                  else nextParams.base_url = baseUrlMode === "secret_ref" ? { secret_ref: event.target.value } : event.target.value;
                  updateParams(nextParams);
                }}
              />
              <small className={styles.formHint}>{baseUrlMode === "secret_ref" ? uiText("只填写 SecretRef 名称。") : uiText("留空则使用提供方默认地址。")}</small>
            </div>
          ) : null}
          {Object.entries(properties)
            .filter(([name, property]) => name !== "api_key" && name !== "base_url" && isRecord(property))
            .map(([name, property]) => <ScalarParameter key={name} name={name} schema={property as JsonObject} params={params} onChange={updateParams} />)}
          <p className={styles.formHint}>{uiText("其他扩展字段仍可在下方“高级依赖 JSON”中编辑。")}</p>
        </>
      )}
    </div>
  );
}
