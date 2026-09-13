import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createStudioAgent, listStudioAgents, type StudioAgent } from "@/entities/agent";
import {
  getStudioFlowTemplateDocument,
  listStudioFlowTemplates,
  parseStudioFlowDocument,
  type StudioFlowDocument,
} from "@/entities/agent-graph";
import styles from "./agentLibrary.module.css";

type AgentCreateIntent = "blank" | "choose" | "example" | "import";

/** Parse supported URL-owned creation modes without treating an unknown query as a command. */
function parseCreateIntent(value: string | null): AgentCreateIntent | null {
  return value === "blank" || value === "choose" || value === "example" || value === "import" ? value : null;
}

/** Format safe mutable metadata without exposing a full opaque identity. */
function formatUpdatedAt(value: number): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(value);
}

/** Return Agents in presentation order without creating a second persisted recent-work truth. */
function sortAgentsByUpdate(agents: readonly StudioAgent[]): StudioAgent[] {
  return [...agents].sort((left, right) => right.updatedAt - left.updatedAt);
}

/** Render the single authoritative Agent discovery and creation surface. */
export function AgentLibraryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const createIntent = parseCreateIntent(params.get("create"));
  const [name, setName] = useState("Research Mobile Agent");
  const [templateId, setTemplateId] = useState("");
  const [search, setSearch] = useState("");
  const [importDiagnostic, setImportDiagnostic] = useState<string | null>(null);
  const importRef = useRef<HTMLInputElement | null>(null);
  const primaryInputRef = useRef<HTMLInputElement | null>(null);
  const importButtonRef = useRef<HTMLButtonElement | null>(null);
  const openingControlRef = useRef<HTMLElement | null>(null);
  const agents = useQuery({
    queryKey: ["studio-agents"],
    queryFn: () => listStudioAgents(50),
    refetchOnMount: "always",
  });
  const templates = useQuery({
    queryKey: ["studio-flow-templates"],
    queryFn: listStudioFlowTemplates,
    enabled: createIntent === "example",
  });
  const createMutation = useMutation({
    mutationFn: async (importedDocument?: StudioFlowDocument) => {
      let initialDocument = importedDocument;
      if (!initialDocument && templateId) {
        const template = await getStudioFlowTemplateDocument(templateId);
        if (template.schemaVersion === 1) {
          throw new Error("该模板仍是旧版 Schema 1，不能创建新的可运行 Agent。");
        } else {
          initialDocument = parseStudioFlowDocument(template);
        }
      }
      return createStudioAgent(
        name.trim() || initialDocument?.name.trim() || "Untitled Agent",
        initialDocument,
      );
    },
    onSuccess: async ({ agent }) => {
      await queryClient.invalidateQueries({ queryKey: ["studio-agents"] });
      navigate(`/agents/${encodeURIComponent(agent.agentId)}/design`);
    },
  });
  const sortedAgents = useMemo(() => sortAgentsByUpdate(agents.data?.items ?? []), [agents.data?.items]);
  const visibleAgents = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase();
    if (!normalized) return sortedAgents;
    return sortedAgents.filter((agent) => agent.name.toLocaleLowerCase().includes(normalized));
  }, [search, sortedAgents]);
  const featuredAgent = useMemo(
    () => sortedAgents.find((agent) => agent.currentRevisionId) ?? sortedAgents[0] ?? null,
    [sortedAgents],
  );
  const duplicateNames = useMemo(() => {
    const counts = new Map<string, number>();
    sortedAgents.forEach((agent) => counts.set(agent.name, (counts.get(agent.name) ?? 0) + 1));
    return counts;
  }, [sortedAgents]);

  useEffect(() => {
    if (createIntent === "example") setTemplateId((current) => current || "modular_baseline");
    if (createIntent === "blank") setTemplateId("");
    if (!createIntent) {
      const opener = openingControlRef.current;
      openingControlRef.current = null;
      opener?.focus();
      return;
    }
    const focusTarget = createIntent === "import" ? importButtonRef.current : primaryInputRef.current;
    focusTarget?.focus();
  }, [createIntent]);

  useEffect(() => {
    if (!createIntent) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || createMutation.isPending) return;
      event.preventDefault();
      closeCreate();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  });

  /** Open a deterministic creation mode and remember the control that opened it for focus return. */
  function startCreate(intent: AgentCreateIntent): void {
    openingControlRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    createMutation.reset();
    setImportDiagnostic(null);
    if (intent === "example") setTemplateId("modular_baseline");
    if (intent === "blank") setTemplateId("");
    const next = new URLSearchParams(params);
    next.set("create", intent);
    setParams(next);
  }

  /** Close only the creation intent while preserving legal unrelated query state. */
  function closeCreate(): void {
    const next = new URLSearchParams(params);
    next.delete("create");
    setParams(next);
    createMutation.reset();
    setImportDiagnostic(null);
  }

  /** Validate or explicitly migrate an imported document before persistence. */
  async function importAgentDocument(raw: unknown): Promise<void> {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("JSON root 必须是对象");
    }
    const record = raw as Record<string, unknown>;
    if (record.schemaVersion !== 3) {
      throw new Error("旧版 Agent 仅可读取与导出；请使用当前能力组件重新搭建后再运行。");
    }
    setImportDiagnostic(null);
    createMutation.mutate(parseStudioFlowDocument(record));
  }

  const isEmptyWorkspace = !agents.isLoading && !agents.isError && sortedAgents.length === 0;
  const hasSearch = Boolean(search.trim());

  return (
    <div className={styles.page}>
      <div className={styles.content}>
        <header className={styles.pageHeader}>
          <div>
            <p className={styles.eyebrow}>Agents</p>
            <h1 className={styles.pageTitle}>你的 Agents</h1>
            <p className={styles.pageCopy}>
              {isEmptyWorkspace ? "从一个可运行的示例开始，或创建空白 Agent。" : "继续设计已有 Agent，或创建新的研究流程。"}
            </p>
          </div>
          {!isEmptyWorkspace ? (
            <button type="button" data-library-action="secondary" className={styles.secondaryAction} onClick={() => startCreate("choose")}>新建 Agent</button>
          ) : null}
        </header>

        {agents.isLoading ? <LibraryState title="正在读取你的 Agents…" /> : agents.isError ? <LibraryState title="无法读取 Agents" detail="请检查 Studio 服务后重试。" action={<button type="button" onClick={() => void agents.refetch()}>重试</button>} /> : isEmptyWorkspace ? (
          <FirstUsePanel onExample={() => startCreate("example")} onBlank={() => startCreate("blank")} onImport={() => startCreate("import")} />
        ) : (
          <section className={styles.librarySection} aria-labelledby="agent-list-heading">
            {featuredAgent ? <ContinuationCard agent={featuredAgent} onOpen={() => navigate(`/agents/${encodeURIComponent(featuredAgent.agentId)}/design`)} /> : null}
            <div className={styles.directoryHeader}>
              <div>
                <h2 id="agent-list-heading" className={styles.directoryTitle}>全部 Agents</h2>
                <p className={styles.directoryCopy}>浏览并打开你的所有 Agent，最近工作也保留在这里。</p>
              </div>
              <input aria-label="搜索 Agent" className={styles.search} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索 Agent 名称" />
            </div>
            {hasSearch && visibleAgents.length === 0 ? <LibraryState title="没有匹配的 Agent" detail="尝试其他名称，或新建一个 Agent。" /> : visibleAgents.length > 0 ? (
              <div className={styles.cardGrid}>
                {visibleAgents.map((agent) => <AgentCard key={agent.agentId} agent={agent} duplicate={duplicateNames.get(agent.name)! > 1} onOpen={() => navigate(`/agents/${encodeURIComponent(agent.agentId)}/design`)} />)}
              </div>
            ) : null}
          </section>
        )}
      </div>

      {createIntent ? (
        <CreateAgentDialog
          intent={createIntent}
          name={name}
          templateId={templateId}
          templates={templates.data ?? []}
          templatesLoading={templates.isLoading}
          pending={createMutation.isPending}
          error={createMutation.isError ? createMutation.error.message : null}
          importDiagnostic={importDiagnostic}
          onPrimaryInput={(element) => { primaryInputRef.current = element; }}
          onImportButton={(element) => { importButtonRef.current = element; }}
          onImportInput={(element) => { importRef.current = element; }}
          onNameChange={setName}
          onTemplateChange={setTemplateId}
          onChoose={(intent) => startCreate(intent)}
          onClose={closeCreate}
          onCreate={() => createMutation.mutate(undefined)}
          onImport={() => importRef.current?.click()}
          onFile={(file) => void file.text().then((text) => importAgentDocument(JSON.parse(text) as unknown)).catch((error: unknown) => {
            createMutation.reset();
            setImportDiagnostic(error instanceof Error ? error.message : "导入失败");
          })}
        />
      ) : null}
    </div>
  );
}

/** Render the first-use choice without prematurely exposing template or migration controls. */
function FirstUsePanel({ onExample, onBlank, onImport }: { onExample: () => void; onBlank: () => void; onImport: () => void }) {
  return <section className={styles.firstUsePanel} aria-labelledby="first-use-heading">
    <p className={styles.eyebrow}>开始研究</p>
    <h2 id="first-use-heading" className={styles.firstUseTitle}>先从一个可理解的 Agent 开始</h2>
    <p className={styles.firstUseCopy}>推荐使用正式示例：你可以先查看完整流程图，再按自己的研究目标修改、验证和运行。</p>
    <div className={styles.firstUseActions}>
      <button type="button" data-library-action="primary" className={styles.firstUsePrimary} onClick={onExample}>从示例开始</button>
      <button type="button" data-library-action="secondary" className={styles.firstUseSecondary} onClick={onBlank}>创建空白 Agent</button>
    </div>
    <button type="button" className={styles.importAction} onClick={onImport}>导入 JSON</button>
  </section>;
}

/** Render the newest resumable Agent using only safe list metadata. */
function ContinuationCard({ agent, onOpen }: { agent: StudioAgent; onOpen: () => void }) {
  const isResumable = Boolean(agent.currentRevisionId);
  return <section className={styles.continuation} aria-labelledby="continue-agent-heading">
    <div className={styles.continuationBody}>
      <div>
        <p className={styles.continuationLabel}>继续上次工作</p>
        <h2 id="continue-agent-heading" className={styles.continuationName}>{agent.name}</h2>
        <p className={styles.continuationMeta}>更新于 {formatUpdatedAt(agent.updatedAt)}</p>
      </div>
      <button type="button" data-library-action="primary" className={styles.continueAction} onClick={onOpen}>{isResumable ? "继续设计" : "打开设计"}</button>
    </div>
  </section>;
}

/** Render one compact Agent directory item using only user-facing metadata. */
function AgentCard({ agent, duplicate, onOpen }: { agent: StudioAgent; duplicate: boolean; onOpen: () => void }) {
  return <button type="button" className={styles.agentCard} onClick={onOpen}>
    <span className={styles.agentCardTop}>
      <strong className={styles.agentName}>{agent.name}</strong>
      <span aria-hidden="true" className={styles.agentArrow}>→</span>
    </span>
    <span className={styles.agentMeta}>更新于 {formatUpdatedAt(agent.updatedAt)}</span>
    {!agent.currentRevisionId ? <span className={styles.draftBadge}>尚未保存版本</span> : null}
    {duplicate ? <span className={styles.duplicateMeta}>同名 Agent · 创建于 {formatUpdatedAt(agent.createdAt)}</span> : null}
  </button>;
}

/** Render an explicit, keyboard-accessible creation or import surface over the Library. */
function CreateAgentDialog({
  intent,
  name,
  templateId,
  templates,
  templatesLoading,
  pending,
  error,
  importDiagnostic,
  onPrimaryInput,
  onImportButton,
  onImportInput,
  onNameChange,
  onTemplateChange,
  onChoose,
  onClose,
  onCreate,
  onImport,
  onFile,
}: {
  intent: AgentCreateIntent;
  name: string;
  templateId: string;
  templates: Array<{ id: string; name: string }>;
  templatesLoading: boolean;
  pending: boolean;
  error: string | null;
  importDiagnostic: string | null;
  onPrimaryInput: (element: HTMLInputElement | null) => void;
  onImportButton: (element: HTMLButtonElement | null) => void;
  onImportInput: (element: HTMLInputElement | null) => void;
  onNameChange: (name: string) => void;
  onTemplateChange: (templateId: string) => void;
  onChoose: (intent: AgentCreateIntent) => void;
  onClose: () => void;
  onCreate: () => void;
  onImport: () => void;
  onFile: (file: File) => void;
}) {
  const isImport = intent === "import";
  const isChoice = intent === "choose";
  const title = isImport ? "导入 Agent JSON" : isChoice ? "新建 Agent" : intent === "example" ? "从示例创建 Agent" : "创建空白 Agent";
  const createDisabled = pending || (intent === "example" && (templatesLoading || !templateId));

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-8" role="presentation">
    <section role="dialog" aria-modal="true" aria-labelledby="create-agent-heading" className="w-full max-w-2xl rounded-2xl border border-[var(--zx-primary-border)] bg-[var(--zx-panel)] p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">Agents</p>
          <h2 id="create-agent-heading" className="mt-1 text-xl font-semibold text-[color:var(--zx-text-title)]">{title}</h2>
        </div>
        <button type="button" aria-label="关闭创建 Agent" disabled={pending} className="rounded-md px-2 py-1 text-[12px] text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-primary-soft)] disabled:opacity-50" onClick={onClose}>关闭</button>
      </div>

      {isChoice ? <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <CreationChoice title="从示例开始" detail="推荐，先查看完整的显式闭环流程。" primary onClick={() => onChoose("example")} />
        <CreationChoice title="创建空白 Agent" detail="从空白 Graph 开始自行搭建。" onClick={() => onChoose("blank")} />
        <CreationChoice title="导入 JSON" detail="导入已有 Studio 文档。" onClick={() => onChoose("import")} />
      </div> : isImport ? <div className="mt-6">
        <p className="text-[13px] leading-relaxed text-[color:var(--zx-text-muted)]">选择已有 Studio JSON。Schema 2 会严格校验；Schema 1 会先显式迁移，原文件不会被修改。</p>
        <button ref={onImportButton} type="button" disabled={pending} className="mt-5 rounded-lg bg-[var(--zx-primary)] px-5 py-2.5 text-[12px] font-semibold text-white disabled:opacity-50" onClick={onImport}>{pending ? "正在导入…" : "选择 JSON 文件"}</button>
      </div> : <div className="mt-6">
        <label className="block text-[12px] font-semibold text-[color:var(--zx-text-title)]">Agent 名称
          <input ref={onPrimaryInput} aria-label="Agent 名称" className="zx-control mt-2 w-full px-3 py-2 text-[12px]" value={name} onChange={(event) => onNameChange(event.target.value)} />
        </label>
        {intent === "example" ? <label className="mt-4 block text-[12px] font-semibold text-[color:var(--zx-text-title)]">正式示例
          <select aria-label="初始模板" className="zx-control mt-2 w-full px-3 py-2 text-[12px]" value={templateId} disabled={templatesLoading} onChange={(event) => onTemplateChange(event.target.value)}>
            {templatesLoading ? <option>正在读取示例…</option> : null}
            {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
          </select>
        </label> : <p className="mt-4 text-[12px] text-[color:var(--zx-text-muted)]">将创建一个空白 AgentGraph 1.1，之后可在设计页面添加组件和流程。</p>}
        <p className="mt-4 text-[11px] text-[color:var(--zx-text-muted)]">此操作只创建持久 Agent 与初始 revision，不会启动模型、设备或 Run。</p>
        <button type="button" disabled={createDisabled} className="mt-6 rounded-lg bg-[var(--zx-primary)] px-5 py-2.5 text-[12px] font-semibold text-white disabled:opacity-50" onClick={onCreate}>{pending ? "正在创建…" : "创建并进入设计"}</button>
      </div>}

      <input ref={onImportInput} hidden type="file" accept="application/json,.json" onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) onFile(file);
      }} />
      {importDiagnostic ? <p role="status" className="mt-4 text-[11px] text-[color:var(--zx-text-muted)]">{importDiagnostic}</p> : null}
      {error ? <p role="alert" className="mt-4 text-[11px] text-[color:var(--zx-status-danger)]">{error}</p> : null}
    </section>
  </div>;
}

/** Render one intent choice within the new-Agent surface. */
function CreationChoice({ title, detail, primary = false, onClick }: { title: string; detail: string; primary?: boolean; onClick: () => void }) {
  return <button type="button" className={`rounded-xl border p-4 text-left transition hover:-translate-y-0.5 ${primary ? "border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)]" : "border-[var(--zx-border-light)] bg-[var(--zx-card)]"}`} onClick={onClick}>
    <strong className="block text-[13px] text-[color:var(--zx-text-title)]">{title}</strong>
    <span className="mt-2 block text-[11px] leading-relaxed text-[color:var(--zx-text-muted)]">{detail}</span>
  </button>;
}

/** Render one isolated Agent Library loading, empty, search-empty, or error state. */
function LibraryState({ title, detail, action }: { title: string; detail?: string; action?: React.ReactNode }) {
  return <div className={styles.state}><strong className={styles.stateTitle}>{title}</strong>{detail ? <p className={styles.stateDetail}>{detail}</p> : null}{action ? <div className={styles.stateAction}>{action}</div> : null}</div>;
}
