import { useEffect, useMemo, useState } from "react";
import type {
  BenchmarkAuthoringRevision,
  BenchmarkAuthoringResource,
} from "@/entities/benchmark-authoring";
import {
  authoringMembers,
  patchManifest,
  patchProtocol,
  selectedAuthoringMember,
} from "../lib/authoringDocument";
import { useBenchmarkDefinitionEditorStore } from "../model/benchmarkDefinitionEditorStore";
import { isRecord, type JsonValue } from "@/shared/lib";

type BenchmarkDefinitionEditorProps = {
  revision: BenchmarkAuthoringRevision;
};

const sectionClass =
  "rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4";
const labelClass =
  "grid gap-1 text-[11px] font-semibold text-[color:var(--zx-text-muted)]";
const inputClass = "zx-control px-3 py-2 text-[12px]";

/**
 * Compose member navigation, one definition editor, and factual revision rail.
 *
 * Args:
 *   props: Exact immutable revision whose detached working copy is being edited.
 *
 * Returns:
 *   The definition-owned member, editor, breadcrumb, and revision surfaces.
 */
export function BenchmarkDefinitionEditor({
  revision,
}: BenchmarkDefinitionEditorProps) {
  const document = useBenchmarkDefinitionEditorStore(
    (state) => state.workingDocument,
  );
  const selectedKey = useBenchmarkDefinitionEditorStore(
    (state) => state.selectedMember,
  );
  const selectMember = useBenchmarkDefinitionEditorStore(
    (state) => state.selectMember,
  );
  const focusedFieldPath = useBenchmarkDefinitionEditorStore(
    (state) => state.focusedFieldPath,
  );
  if (!document) return null;
  const members = authoringMembers(document);
  const selected = selectedAuthoringMember(document, selectedKey);

  return (
    <div className="grid min-h-0 flex-1 lg:grid-cols-[15rem_minmax(22rem,1fr)_20rem]">
      <nav
        aria-label="Package members"
        className="min-h-0 overflow-auto border-r border-[var(--zx-divider-ui)] p-3"
      >
        <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-text-muted)]">
          Package members
        </p>
        <div className="space-y-1">
          {members.map((member) => (
            <button
              key={member.key}
              type="button"
              onClick={() => selectMember(member.key)}
              className={[
                "w-full rounded-lg px-3 py-2 text-left text-[11px]",
                member.key === selected.key
                  ? "bg-[var(--zx-primary-soft)] font-semibold text-[color:var(--zx-text-title)]"
                  : "text-[color:var(--zx-text-muted)] hover:bg-black/10",
              ].join(" ")}
            >
              <span className="block text-[9px] uppercase opacity-70">
                {member.kind}
              </span>
              <span className="mt-0.5 block truncate">{member.label}</span>
            </button>
          ))}
        </div>
      </nav>

      <main className="min-h-0 overflow-auto p-5">
        {focusedFieldPath.length > 0 ? (
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[10px] text-amber-300">
            Diagnostic field path: <span className="font-mono">{focusedFieldPath.map(
              (item) => typeof item === "number" ? `[${item}]` : `.${item}`,
            ).join("")}</span>. 当前编辑器不承诺对 open JSON 路径提供 caret-level focus。
          </div>
        ) : null}
        {selected.kind === "manifest" ? <ManifestEditor /> : null}
        {selected.kind === "protocol" ? (
          <ProtocolEditor protocolPath={selected.path} />
        ) : null}
        {selected.kind === "task" ? (
          <TaskFileEditor taskPath={selected.path} />
        ) : null}
        {selected.kind === "resource" ? (
          <ResourceEditor
            resource={
              document.resources.find(
                (resource) => resource.id === selected.resourceId,
              ) ?? null
            }
          />
        ) : null}
      </main>

      <RevisionFacts revision={revision} />
    </div>
  );
}

/** Edit known manifest fields with path patches over the open mapping. */
function ManifestEditor() {
  const document = useBenchmarkDefinitionEditorStore(
    (state) => state.workingDocument,
  )!;
  const replace = useBenchmarkDefinitionEditorStore(
    (state) => state.replaceWorkingDocument,
  );
  const manifest = document.manifest.document;
  const identity = isRecord(manifest.identity) ? manifest.identity : {};
  const platforms = Array.isArray(manifest.platforms)
    ? manifest.platforms.filter((item): item is string => typeof item === "string")
    : [];
  const splits = isRecord(manifest.splits) ? manifest.splits : {};

  /** Patch one known manifest field while retaining all unrelated mappings. */
  const update = (path: readonly (string | number)[], value: JsonValue) => {
    replace(patchManifest(document, path, value));
  };

  return (
    <div className="space-y-4">
      <EditorHeading
        title="Benchmark manifest"
        detail="字段组合尚未经过正式校验；未知扩展字段会原样保留。"
      />
      <section className={sectionClass}>
        <h3 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">
          Package identity
        </h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {(["publisher", "name", "version"] as const).map((field) => (
            <label key={field} className={labelClass}>
              {field}
              <input
                className={inputClass}
                value={typeof identity[field] === "string" ? identity[field] : ""}
                onChange={(event) =>
                  update(["identity", field], event.target.value)}
              />
            </label>
          ))}
        </div>
      </section>
      <section className={sectionClass}>
        <div className="grid gap-3">
          <label className={labelClass}>
            Title
            <input
              className={inputClass}
              value={typeof manifest.title === "string" ? manifest.title : ""}
              onChange={(event) => update(["title"], event.target.value)}
            />
          </label>
          <label className={labelClass}>
            Platforms (comma-separated)
            <input
              className={inputClass}
              value={platforms.join(", ")}
              onChange={(event) =>
                update(
                  ["platforms"],
                  event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                )}
            />
          </label>
          <label className={labelClass}>
            Default Protocol member
            <input
              className={inputClass}
              value={
                typeof manifest.default_protocol === "string"
                  ? manifest.default_protocol
                  : ""
              }
              onChange={(event) =>
                update(["default_protocol"], event.target.value)}
            />
          </label>
        </div>
      </section>
      <section className={sectionClass}>
        <h3 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">
          Split membership
        </h3>
        <div className="mt-3 space-y-3">
          {Object.entries(splits).map(([name, split]) => {
            const mapping = isRecord(split) ? split : {};
            const files = Array.isArray(mapping.files)
              ? mapping.files.filter(
                  (item): item is string => typeof item === "string",
                )
              : [];
            return (
              <label key={name} className={labelClass}>
                {name} task files
                <input
                  className={inputClass}
                  value={files.join(", ")}
                  onChange={(event) =>
                    update(
                      ["splits", name, "files"],
                      event.target.value
                        .split(",")
                        .map((item) => item.trim())
                        .filter(Boolean),
                    )}
                />
              </label>
            );
          })}
          {Object.keys(splits).length === 0 ? (
            <p className="text-[11px] text-[color:var(--zx-text-muted)]">
              当前 manifest 没有 split 映射。
            </p>
          ) : null}
        </div>
      </section>
      <JsonMappingField
        label="Applications"
        value={manifest.applications ?? []}
        onApply={(value) => update(["applications"], value)}
      />
      <JsonMappingField
        label="Plugins"
        value={manifest.plugins ?? []}
        onApply={(value) => update(["plugins"], value)}
      />
      <JsonMappingField
        label="Inline ground truth definition"
        value={manifest.ground_truth ?? {}}
        onApply={(value) => update(["ground_truth"], value)}
      />
    </div>
  );
}

/** Edit the selected Protocol mapping without claiming semantic validity. */
function ProtocolEditor({ protocolPath }: { protocolPath: string }) {
  const document = useBenchmarkDefinitionEditorStore(
    (state) => state.workingDocument,
  )!;
  const replace = useBenchmarkDefinitionEditorStore(
    (state) => state.replaceWorkingDocument,
  );
  const protocol = document.protocolFiles.find(
    (item) => item.path === protocolPath,
  );
  if (!protocol) return <EditorHeading title="Protocol missing" detail={protocolPath} />;

  /** Patch one known Protocol field through the lossless document helper. */
  const update = (path: readonly (string | number)[], value: JsonValue) => {
    replace(patchProtocol(document, protocolPath, path, value));
  };

  return (
    <div className="space-y-4">
      <EditorHeading
        title={protocolPath}
        detail="Protocol 仍为 unvalidated；这里只编辑定义，不生成 schedule。"
      />
      <section className={sectionClass}>
        <div className="grid gap-3 sm:grid-cols-2">
          {(["seed", "repeats"] as const).map((field) => (
            <label key={field} className={labelClass}>
              {field}
              <input
                type="number"
                className={inputClass}
                value={
                  typeof protocol.document[field] === "number"
                    ? protocol.document[field]
                    : 0
                }
                onChange={(event) => update([field], Number(event.target.value))}
              />
            </label>
          ))}
        </div>
      </section>
      <JsonMappingField
        label="Protocol budget"
        value={protocol.document.budget ?? {}}
        onApply={(value) => update(["budget"], value)}
      />
    </div>
  );
}

/** Keep task source text local until a deliberate safe array apply. */
function TaskFileEditor({ taskPath }: { taskPath: string }) {
  const buffer = useBenchmarkDefinitionEditorStore(
    (state) => state.taskBuffers[taskPath],
  );
  const update = useBenchmarkDefinitionEditorStore(
    (state) => state.updateTaskBuffer,
  );
  const apply = useBenchmarkDefinitionEditorStore(
    (state) => state.applyTaskBuffer,
  );
  if (!buffer) return <EditorHeading title="Task file missing" detail={taskPath} />;
  const unapplied = buffer.text !== buffer.appliedText;
  const errorId = `task-buffer-error-${taskPath.replaceAll(/[^a-z0-9]/gi, "-")}`;
  return (
    <div className="space-y-4">
      <EditorHeading
        title={taskPath}
        detail="原始 JSON 仅存在于当前浏览器内存；Apply JSON 后才进入可保存文档。"
      />
      <textarea
        aria-label={`Task JSON ${taskPath}`}
        aria-describedby={buffer.error ? errorId : undefined}
        spellCheck={false}
        className="zx-control min-h-[30rem] w-full resize-y p-4 font-mono text-[12px] leading-5"
        value={buffer.text}
        onChange={(event) => update(taskPath, event.target.value)}
      />
      {buffer.error ? (
        <p id={errorId} role="alert" className="text-[11px] text-rose-400">
          {buffer.error.line
            ? `Line ${buffer.error.line}, column ${buffer.error.column}: `
            : ""}
          {buffer.error.message}
        </p>
      ) : unapplied ? (
        <p className="text-[11px] text-amber-400">
          JSON 语法可解析但尚未 Apply；Save 已阻止。
        </p>
      ) : (
        <p className="text-[11px] text-emerald-400">
          当前 buffer 已应用到 parsed document。
        </p>
      )}
      <button
        type="button"
        onClick={() => apply(taskPath)}
        className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[12px] font-semibold text-white"
      >
        Apply JSON
      </button>
    </div>
  );
}

/** Show immutable resource facts without constructing a bearer capability. */
function ResourceEditor({
  resource,
}: {
  resource: BenchmarkAuthoringResource | null;
}) {
  if (!resource) return <EditorHeading title="Resource missing" detail="" />;
  return (
    <div className="space-y-4">
      <EditorHeading
        title={resource.path}
        detail="Metadata only · read-only。此版本不提供预览、上传、替换或删除。"
      />
      <section className={sectionClass}>
        <Fact label="Logical ID" value={resource.id} />
        <Fact label="Kind" value={resource.kind} />
        <Fact label="Media type" value={resource.mediaType} />
        <Fact label="Size" value={`${resource.size} bytes`} />
        <Fact label="SHA-256" value={resource.sha256} mono />
        <Fact label="Content identity" value={resource.contentIdentity} mono />
      </section>
    </div>
  );
}

/** Edit one known JSON-valued property with explicit local parse/apply. */
function JsonMappingField({
  label,
  value,
  onApply,
}: {
  label: string;
  value: JsonValue;
  onApply: (value: JsonValue) => void;
}) {
  const serialized = useMemo(() => JSON.stringify(value, null, 2), [value]);
  const [text, setText] = useState(serialized);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(serialized);
    setError(null);
  }, [serialized]);

  /** Parse and commit this one known field while surfacing local syntax errors. */
  const apply = () => {
    try {
      const parsed: unknown = JSON.parse(text);
      onApply(parsed as JsonValue);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid JSON");
    }
  };

  return (
    <section className={sectionClass}>
      <label className={labelClass}>
        {label}
        <textarea
          className="zx-control min-h-32 resize-y p-3 font-mono text-[11px]"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      {error ? <p role="alert" className="mt-2 text-[11px] text-rose-400">{error}</p> : null}
      <button
        type="button"
        onClick={apply}
        className="mt-3 rounded-lg border border-[var(--zx-primary-border)] px-3 py-2 text-[11px] font-semibold text-[color:var(--zx-text-title)]"
      >
        Apply field
      </button>
    </section>
  );
}

/** Render immutable revision, provenance, and document fingerprint facts. */
function RevisionFacts({ revision }: { revision: BenchmarkAuthoringRevision }) {
  return (
    <aside className="min-h-0 overflow-auto border-l border-[var(--zx-divider-ui)] p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-text-muted)]">
        Revision facts
      </p>
      <section className={`${sectionClass} mt-3`}>
        <Fact label="Status" value="unvalidated" />
        <Fact label="Ordinal" value={String(revision.ordinal)} />
        <Fact label="Revision" value={revision.revisionId} mono />
        <Fact label="Parent" value={revision.parentRevisionId ?? "initial"} mono />
        <Fact label="Fingerprint" value={revision.documentFingerprint} mono />
        <Fact label="Source" value={revision.provenance.sourceKind} />
        <Fact
          label="Template"
          value={revision.provenance.templateName ?? "—"}
        />
        <Fact
          label="Catalog entry"
          value={revision.provenance.catalogEntryId ?? "—"}
          mono
        />
      </section>
      <p className="mt-4 text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
        本页不执行 Validate、Run、Publish、Export，也不会解析设备、插件、模型或密钥。
      </p>
    </aside>
  );
}

/** Render one editor title with a truthful scope description. */
function EditorHeading({ title, detail }: { title: string; detail: string }) {
  return (
    <header>
      <h2 className="text-[16px] font-semibold text-[color:var(--zx-text-title)]">
        {title}
      </h2>
      <p className="mt-1 text-[11px] text-[color:var(--zx-text-muted)]">
        {detail}
      </p>
    </header>
  );
}

/** Render one compact factual label/value pair. */
function Fact({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="border-b border-[var(--zx-divider-ui)] py-2 last:border-0">
      <dt className="text-[9px] uppercase tracking-wide text-[color:var(--zx-text-muted)]">
        {label}
      </dt>
      <dd
        className={[
          "mt-1 break-all text-[10px] text-[color:var(--zx-text-body)]",
          mono ? "font-mono" : "",
        ].join(" ")}
      >
        {value}
      </dd>
    </div>
  );
}
