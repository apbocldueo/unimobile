import { uiText, useUiLocale } from "@/shared/i18n";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { createStudioAgent, listStudioAgents, type StudioAgent } from "@/entities/agent";
import {
  getStudioFlowTemplateDocument,
  listStudioFlowTemplates,
  parseStudioFlowDocument,
  type StudioFlowDocument,
} from "@/entities/agent-graph";
import { RecentRunReturn } from "@/features/recent-run-return";
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
  const uiLocale = useUiLocale();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const createIntent = parseCreateIntent(params.get("create"));
  const [name, setName] = useState("Research Mobile Agent");
  const [templateId, setTemplateId] = useState("");
  const [search, setSearch] = useState("");
  const [importDiagnostic, setImportDiagnostic] = useState<string | null>(null);
  const createDestination = useRef<"design" | "run">("design");
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
          throw new Error(uiText("该模板仍是旧版 Schema 1，不能创建新的可运行 Agent。"));
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
      navigate(`/agents/${encodeURIComponent(agent.agentId)}/${createDestination.current}`);
    },
  });
  const sortedAgents = useMemo(() => sortAgentsByUpdate(agents.data?.items ?? []), [agents.data?.items, uiLocale]);
  const visibleAgents = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase();
    if (!normalized) return sortedAgents;
    return sortedAgents.filter((agent) => agent.name.toLocaleLowerCase().includes(normalized));
  }, [search, sortedAgents, uiLocale]);
  const duplicateNames = useMemo(() => {
    const counts = new Map<string, number>();
    sortedAgents.forEach((agent) => counts.set(agent.name, (counts.get(agent.name) ?? 0) + 1));
    return counts;
  }, [sortedAgents, uiLocale]);

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
      throw new Error(uiText("JSON root 必须是对象"));
    }
    const record = raw as Record<string, unknown>;
    if (record.schemaVersion !== 3) {
      throw new Error(uiText("旧版 Agent 仅可读取与导出；请使用当前能力组件重新搭建后再运行。"));
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
            <h1 className={styles.pageTitle}>{uiText("我的 Agents")}</h1>
            <p className={styles.pageCopy}>
              {isEmptyWorkspace ? uiText("从示例创建你的第一个 Agent，也可以导入或自行搭建。") : uiText("选择自己的 Agent 开始任务，也可以继续编辑它的能力。")}
            </p>
          </div>
          {!isEmptyWorkspace ? (
            <button type="button" data-library-action="secondary" className={styles.secondaryAction} onClick={() => startCreate("choose")}>{uiText("新建 Agent")}</button>
          ) : null}
        </header>
        <p className={styles.preparationHelp}>{uiText("需要配置模型或设备？")}<Link to="/settings">{uiText("打开设置")}</Link><span> · </span><Link to="/help?topic=start">{uiText("使用指南")}</Link></p>

        <RecentRunReturn />
        {agents.isLoading ? <LibraryState title={uiText("正在读取你的 Agents…")} /> : agents.isError ? <LibraryState title={uiText("无法读取 Agents")} detail={uiText("请检查 Studio 服务后重试。")} action={<button type="button" onClick={() => void agents.refetch()}>{uiText("重试")}</button>} /> : isEmptyWorkspace ? (
          <FirstUsePanel onExample={() => startCreate("example")} onBlank={() => startCreate("blank")} onImport={() => startCreate("import")} />
        ) : (
          <section className={styles.librarySection} aria-labelledby="agent-list-heading">

            <div className={styles.directoryHeader}>
              <div>
                <h2 id="agent-list-heading" className={styles.directoryTitle}>{uiText("全部 Agents")}</h2>
                <p className={styles.directoryCopy}>{uiText("按最近更新时间排列 · 开始任务后选择设备并检查运行配置。")}</p>
              </div>
              <input aria-label={uiText("搜索 Agent")} className={styles.search} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={uiText("搜索 Agent 名称")} />
            </div>
            {hasSearch && visibleAgents.length === 0 ? <LibraryState title={uiText("没有匹配的 Agent")} detail={uiText("尝试其他名称，或新建一个 Agent。")} /> : visibleAgents.length > 0 ? (
              <div className={styles.cardGrid}>
                {visibleAgents.map((agent) => <AgentCard key={agent.agentId} agent={agent} duplicate={duplicateNames.get(agent.name)! > 1} />)}
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
          onCreate={() => { createDestination.current = "design"; createMutation.mutate(undefined); }}
          onCreateRun={() => { createDestination.current = "run"; createMutation.mutate(undefined); }}
          onImport={() => importRef.current?.click()}
          onFile={(file) => void file.text().then((text) => importAgentDocument(JSON.parse(text) as unknown)).catch((error: unknown) => {
            createMutation.reset();
            setImportDiagnostic(error instanceof Error ? error.message : uiText("导入失败"));
          })}
        />
      ) : null}
    </div>
  );
}

/** Render the first-use choice without prematurely exposing template or migration controls. */
function FirstUsePanel({ onExample, onBlank, onImport }: { onExample: () => void; onBlank: () => void; onImport: () => void }) {
  useUiLocale();
  return <section className={styles.firstUsePanel} aria-labelledby="first-use-heading">
    <p className={styles.eyebrow}>{uiText("欢迎使用知行")}</p>
    <h2 id="first-use-heading" className={styles.firstUseTitle}>{uiText("创建你的第一个 Agent")}</h2>
    <p className={styles.firstUseCopy}>{uiText("从示例创建后，可以直接准备一次任务，也可以先编辑 Agent。模型与设备会在运行前检查。")}</p>
    <div className={styles.firstUseActions}>
      <button type="button" data-library-action="primary" className={styles.firstUsePrimary} onClick={onExample}>{uiText("从示例开始")}</button>
      <button type="button" data-library-action="secondary" className={styles.firstUseSecondary} onClick={onBlank}>{uiText("创建空白 Agent")}</button>
    </div>
    <button type="button" className={styles.importAction} onClick={onImport}>{uiText("导入 JSON")}</button>
  </section>;
}

/** Present explicit preparation, editing and history links for one personal Agent. */
function AgentCard({ agent, duplicate }: { agent: StudioAgent; duplicate: boolean }) {
  useUiLocale();
  const base = `/agents/${encodeURIComponent(agent.agentId)}`;
  return <article className={styles.agentCard} aria-label={agent.name}>
    <div className={styles.agentCardTop}><Link to={`${base}/design`} className={styles.agentName}>{agent.name}</Link></div>
    <span className={styles.agentMeta}>{uiText("更新于")}{" "}{formatUpdatedAt(agent.updatedAt)}</span>
    <span className={styles.draftBadge}>{agent.currentRevisionId ? uiText("已有保存版本") : uiText("尚未保存版本 · 先完成编辑")}</span>
    {duplicate ? <span className={styles.duplicateMeta}>{uiText("同名 Agent · 创建于")}{" "}{formatUpdatedAt(agent.createdAt)}</span> : null}
    <div className={styles.cardActions}>
      {agent.currentRevisionId ? <Link className={styles.runAction} to={`${base}/run`}>{uiText("开始任务 ↗")}</Link> : null}
      <Link to={`${base}/design`}>{uiText("编辑")}</Link><Link to={`${base}/runs`}>{uiText("运行记录")}</Link>
    </div>
  </article>;
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
  onCreateRun,
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
  onCreateRun: () => void;
  onImport: () => void;
  onFile: (file: File) => void;
}) {
  const uiLocale = useUiLocale();
  const isImport = intent === "import";
  const isChoice = intent === "choose";
  const title = isImport ? uiText("导入 Agent JSON") : isChoice ? uiText("新建 Agent") : intent === "example" ? uiText("从示例创建 Agent") : uiText("创建空白 Agent");
  const createDisabled = pending || (intent === "example" && (templatesLoading || !templateId));

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-8" role="presentation">
    <section role="dialog" aria-modal="true" aria-labelledby="create-agent-heading" className="w-full max-w-2xl rounded-2xl border border-[var(--zx-primary-border)] bg-[var(--zx-panel)] p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">Agents</p>
          <h2 id="create-agent-heading" className="mt-1 text-xl font-semibold text-[color:var(--zx-text-title)]">{title}</h2>
        </div>
        <button type="button" aria-label={uiText("关闭创建 Agent")} disabled={pending} className="rounded-md px-2 py-1 text-[12px] text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-primary-soft)] disabled:opacity-50" onClick={onClose}>{uiText("关闭")}</button>
      </div>

      {isChoice ? <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <CreationChoice title={uiText("从示例开始")} detail={uiText("推荐，先查看完整的显式闭环流程。")} primary onClick={() => onChoose("example")} />
        <CreationChoice title={uiText("创建空白 Agent")} detail={uiText("从空白 Graph 开始自行搭建。")} onClick={() => onChoose("blank")} />
        <CreationChoice title={uiText("导入 JSON")} detail={uiText("导入已有 Studio 文档。")} onClick={() => onChoose("import")} />
      </div> : isImport ? <div className="mt-6">
        <p className="text-[13px] leading-relaxed text-[color:var(--zx-text-muted)]">{uiText("选择当前版本的 Studio Agent JSON（Schema 3）。旧版文档暂不支持导入运行，原文件不会被修改。")}</p>
        <button ref={onImportButton} type="button" disabled={pending} className="mt-5 rounded-lg bg-[var(--zx-primary)] px-5 py-2.5 text-[12px] font-semibold text-white disabled:opacity-50" onClick={onImport}>{pending ? uiText("正在导入…") : uiText("选择 JSON 文件")}</button>
      </div> : <div className="mt-6">
        <label className="block text-[12px] font-semibold text-[color:var(--zx-text-title)]">{uiText("Agent 名称")}<input ref={onPrimaryInput} aria-label={uiText("Agent 名称")} className="zx-control mt-2 w-full px-3 py-2 text-[12px]" value={name} onChange={(event) => onNameChange(event.target.value)} />
        </label>
        {intent === "example" ? <label className="mt-4 block text-[12px] font-semibold text-[color:var(--zx-text-title)]">{uiText("正式示例")}<select aria-label={uiText("初始模板")} className="zx-control mt-2 w-full px-3 py-2 text-[12px]" value={templateId} disabled={templatesLoading} onChange={(event) => onTemplateChange(event.target.value)}>
            {templatesLoading ? <option>{uiText("正在读取示例…")}</option> : null}
            {templates.map((template) => <option key={template.id} value={template.id}>{template.id === "modular_baseline" && uiLocale === "en" ? uiText("Mobile Agent 显式闭环（推荐）") : template.name}</option>)}
          </select>
        </label> : <p className="mt-4 text-[12px] text-[color:var(--zx-text-muted)]">{uiText("将创建一个空白 AgentGraph 1.1，之后可在设计页面添加组件和流程。")}</p>}
        <p className="mt-4 text-[11px] text-[color:var(--zx-text-muted)]">{uiText("创建后可以先试跑，也可以编辑流程。只有在运行页提交任务才会调用模型与设备。")}</p>
        {intent === "example" ? <div className="mt-4 rounded-lg border border-[var(--zx-border-light)] p-4 text-[13px] leading-relaxed">
          <strong>{uiText("先确认手机画面，再尝试导航")}</strong>
          <p>{uiText("示例已包含观察、判断和行动流程。需要已配置的模型接口与 Android 设备。")}</p>
          <p>{uiText("首次可手动打开系统设置首页，在运行页填入观察示例；预期看到截图并结束，不修改手机设置。")}</p>
          <button type="button" disabled={createDisabled} className="mt-3 rounded-lg bg-[var(--zx-primary)] px-5 py-2 text-white disabled:opacity-50" onClick={onCreateRun}>{pending ? uiText("正在创建…") : uiText("创建并准备试跑")}</button>
        </div> : null}
        <button type="button" disabled={createDisabled} className="mt-6 rounded-lg bg-[var(--zx-primary)] px-5 py-2.5 text-[12px] font-semibold text-white disabled:opacity-50" onClick={onCreate}>{pending ? uiText("正在创建…") : uiText("创建并进入设计")}</button>
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
  useUiLocale();
  return <button type="button" className={`rounded-xl border p-4 text-left transition hover:-translate-y-0.5 ${primary ? "border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)]" : "border-[var(--zx-border-light)] bg-[var(--zx-card)]"}`} onClick={onClick}>
    <strong className="block text-[13px] text-[color:var(--zx-text-title)]">{title}</strong>
    <span className="mt-2 block text-[11px] leading-relaxed text-[color:var(--zx-text-muted)]">{detail}</span>
  </button>;
}

/** Render one isolated Agent Library loading, empty, search-empty, or error state. */
function LibraryState({ title, detail, action }: { title: string; detail?: string; action?: React.ReactNode }) {
  useUiLocale();
  return <div className={styles.state}><strong className={styles.stateTitle}>{title}</strong>{detail ? <p className={styles.stateDetail}>{detail}</p> : null}{action ? <div className={styles.stateAction}>{action}</div> : null}</div>;
}
