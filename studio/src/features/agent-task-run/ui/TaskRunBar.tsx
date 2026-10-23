import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { useEffect, useRef, useState } from "react";
import {
  useCancelStudioRun,
  useCreateStudioRun,
  type CreateStudioRunResponse,
  type StudioRunResource,
} from "@/entities/run";
import {
  useExactRevisionReadiness,
  useSafeDeviceProfiles,
  readinessRemediation,
  type RuntimeReadinessDiagnostic,
} from "@/entities/runtime-readiness";
import {
  newTaskRunRequestId,
  prepareTaskRun,
  type AgentRunTarget,
} from "../model/taskRunDraft";
import styles from "./taskRunBar.module.css";

type TaskRunBarProps = {
  target: AgentRunTarget;
  onCreated: (run: CreateStudioRunResponse) => void;
  autoFocus?: boolean;
  sourceTask?: { text: string; metadata: import("@/shared/lib").JsonValue };
};

const PROFILE_PREFERENCE_KEY = "zx-studio-run-profile-v1";

const TOPOLOGY_REASON_BY_CODE: Record<string, string> = {
  /** Read this static UI label in the selected language. */ get "studio.readiness.topology_observation_missing"() { return uiText("内部运行图缺少设备观察入口。"); },
  /** Read this static UI label in the selected language. */ get "studio.readiness.topology_action_executor_missing"() { return uiText("内部运行图缺少设备动作执行边界。"); },
  /** Read this static UI label in the selected language. */ get "studio.readiness.topology_legacy_action_executor"() { return uiText("内部运行图仍在使用旧版动作执行边界。"); },
  /** Read this static UI label in the selected language. */ get "studio.readiness.topology_action_request_missing"() { return uiText("内部运行图无法把能力输出转换为设备动作请求。"); },
  /** Read this static UI label in the selected language. */ get "studio.readiness.topology_terminal_gate_missing"() { return uiText("内部运行图缺少明确的结束路径。"); },
  /** Read this static UI label in the selected language. */ get "studio.readiness.topology_feedback_missing"() { return uiText("内部运行图没有形成受限的下一轮执行路径。"); },
  /** Read this static UI label in the selected language. */ get "studio.readiness.topology_policy_unbounded"() { return uiText("内部运行图的执行上限配置不一致。"); },
};

/** Present one readiness failure without exposing authoring-hidden flow components. */
function describeReadinessDiagnostic(item: RuntimeReadinessDiagnostic): string {
  const message = item.category === "topology"
    ? TOPOLOGY_REASON_BY_CODE[item.code] ?? uiText("内部 Android 运行拓扑未通过校验。")
    : item.message;
  return `${message}（${item.code}）`;
}

/** Read only the optional safe device-profile preference. */
function storedProfilePreference(): string {
  try {
    return window.localStorage.getItem(PROFILE_PREFERENCE_KEY) ?? "";
  } catch {
    return "";
  }
}

/** Render and submit one non-persistent ordinary task draft for an exact revision. */
export function TaskRunBar({ target, onCreated, autoFocus = false, sourceTask }: TaskRunBarProps) {
  useUiLocale();
  const [taskText, setTaskText] = useState("");
  const [metadataText, setMetadataText] = useState("{}");
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const [deviceProfileId, setDeviceProfileId] = useState(storedProfilePreference);
  const [checkingReadiness, setCheckingReadiness] = useState(false);
  const requestIdentity = useRef<{ semantic: string; value: string } | null>(null);
  const createRun = useCreateStudioRun();
  const profiles = useSafeDeviceProfiles();
  const profileItems = profiles.data?.items ?? [];
  useEffect(() => {
    if (!profiles.data) return;
    const valid = profileItems.some((item) => item.deviceProfileId === deviceProfileId);
    const next = valid ? deviceProfileId : profileItems.length === 1 ? profileItems[0]!.deviceProfileId : "";
    if (next !== deviceProfileId) setDeviceProfileId(next);
    try {
      if (next) window.localStorage.setItem(PROFILE_PREFERENCE_KEY, next);
      else window.localStorage.removeItem(PROFILE_PREFERENCE_KEY);
    } catch {
      // Profile identity is an optional non-semantic preference only.
    }
  }, [deviceProfileId, profileItems, profiles.data]);
  const readiness = useExactRevisionReadiness(
    target.agentId,
    target.revisionId,
    deviceProfileId,
  );
  const eligible = Boolean(
    deviceProfileId
    && !checkingReadiness
    && !createRun.isPending,
  );
  const topologyDiagnostics = readiness.data?.diagnostics.filter(
    (item) => item.category === "topology",
  ) ?? [];
  const blockingMessages = Array.from(new Set(
    readiness.data?.diagnostics.map(describeReadinessDiagnostic) ?? [],
  ));

  /** Validate the draft, preserve uncertain retry identity, and bind the created Run. */
  const submit = async () => {
    let prepared;
    try {
      prepared = prepareTaskRun(target, deviceProfileId, taskText, metadataText);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : uiText("普通 task 无效。"));
      return;
    }
    if (requestIdentity.current?.semantic !== prepared.semanticIdentity) {
      requestIdentity.current = {
        semantic: prepared.semanticIdentity,
        value: newTaskRunRequestId(),
      };
    }
    setFormError("");
    setCheckingReadiness(true);
    try {
      const checked = await readiness.refetch({ cancelRefetch: true });
      if (checked.isError || !checked.data) {
        setFormError(uiText("无法从后端重新检查运行条件，请确认 Studio 服务正在运行后重试。"));
        return;
      }
      if (!checked.data.ready) {
        setFormError(
          uiMessage`当前不能运行：${checked.data.diagnostics.map(describeReadinessDiagnostic).join("；")}`,
        );
        return;
      }
      const run = await createRun.mutateAsync({
        schemaVersion: 1,
        clientRequestId: requestIdentity.current.value,
        agentId: target.agentId,
        revisionId: target.revisionId,
        task: prepared.task,
        deviceProfileId,
        runtimeKind: "android",
      });
      onCreated(run);
    } catch {
      // The typed mutation error is rendered below while the same semantic retry remains stable.
    } finally {
      setCheckingReadiness(false);
    }
  };

  return (
    <form
      className={styles.bar}
      aria-label="Task Run Bar"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <label className={styles.task}>
        <span>{sourceTask ? uiText("新任务") : uiText("任务")}</span>
        <textarea
          aria-label="Task"
          autoFocus={autoFocus}
          maxLength={32768}
          rows={1}
          value={taskText}
          onChange={(event) => setTaskText(event.target.value)}
          placeholder={uiText("描述目标与结束条件，或填入观察示例")}
        />
      </label>
      <label className={styles.profile}>
        <span>{uiText("设备")}</span>
        {profileItems.length > 1 ? (
          <select
            aria-label="Device Profile"
            value={deviceProfileId}
            onChange={(event) => {
              const next = event.target.value;
              setDeviceProfileId(next);
              try {
                if (next) window.localStorage.setItem(PROFILE_PREFERENCE_KEY, next);
              } catch {
                // Safe preference persistence is optional.
              }
            }}
          >
            <option value="">{uiText("请选择")}</option>
            {profileItems.map((profile) => (
              <option key={profile.deviceProfileId} value={profile.deviceProfileId}>
                {profile.label}
              </option>
            ))}
          </select>
        ) : (
          <strong>{profileItems[0]?.label ?? uiText("未配置")}</strong>
        )}
      </label>
      <button type="button" className={styles.metadataToggle} disabled={checkingReadiness || createRun.isPending} onClick={() => {
        if (taskText.trim() && !window.confirm(uiText("替换当前尚未提交的任务内容？"))) return;
        setTaskText(sourceTask?.text ?? uiText("确认当前屏幕是否为 Android 系统设置首页。如果是，立即结束；如果不是，说明情况并结束。不要点击，不要修改任何设置。"));
        setMetadataText(sourceTask ? JSON.stringify(sourceTask.metadata, null, 2) : "{}");
        setFormError("");
      }}>{sourceTask ? uiText("复制原任务") : uiText("填入观察示例")}</button>
      <button
        type="button"
        className={styles.metadataToggle}
        onClick={() => setMetadataOpen((open) => !open)}
      >
        {metadataOpen ? uiText("收起附加信息") : uiText("附加信息")}
      </button>
      <button type="submit" className={styles.run} disabled={!eligible}>
        {checkingReadiness ? uiText("检查中…") : createRun.isPending ? uiText("提交中…") : uiText("运行")}
      </button>
      {metadataOpen ? (
        <label className={styles.metadata}>
          <span>{uiText("metadata JSON（可选）")}</span>
          <textarea
            aria-label="metadata JSON"
            rows={4}
            value={metadataText}
            onChange={(event) => setMetadataText(event.target.value)}
          />
        </label>
      ) : null}
      {formError ? <p className={styles.error}>{formError}</p> : null}
      {profiles.isError ? (
        <p className={styles.error}>{uiText("无法读取 Device Profiles：")}{profiles.error instanceof Error ? profiles.error.message : "unknown"}</p>
      ) : null}
      {profiles.data && profileItems.length === 0 ? (
        <p className={styles.error}>{uiText("当前服务未配置 Device Profile；请在设置 → 运行环境中查看启动方式。")}{" "}<a href="/help?topic=device" target="_blank" rel="noopener noreferrer">{uiText("设备配置说明 ↗")}</a></p>
      ) : null}
      <section aria-label="Run preparation" className={styles.readiness}>
        <p>{sourceTask ? uiText("复制后可编辑任务，再显式提交新运行；原记录不变。") : uiText("观察示例请先手动打开系统设置首页。运行会调用模型，可能产生接口费用。")}</p>
        <p>{!deviceProfileId ? uiText("请先选择已配置的设备。") : readiness.isError ? uiText("暂时无法读取配置检查结果，请重试。") : readiness.isFetching ? uiText("正在检查配置…") : readiness.isStale ? uiText("上次配置结果待复查，提交时会再次检查。") : uiText("静态配置检查不代表实际连接成功；提交时会再次核验此版本与设备配置。")}</p>
        {readiness.data && !readiness.isError && !readiness.isFetching && readiness.data.agentId === target.agentId && readiness.data.revisionId === target.revisionId && readiness.data.deviceProfileId === deviceProfileId ? readiness.data.diagnostics.map((diagnostic, index) => {
          const next = readinessRemediation(diagnostic);
          return <div key={`${diagnostic.code}-${index}`}><p>{next.instruction}</p><a href={`/help?topic=${next.preparation}`} target="_blank" rel="noopener noreferrer">{uiText("查看处理步骤 ↗")}</a></div>;
        }) : null}
        <button type="button" disabled={!deviceProfileId || readiness.isFetching} onClick={() => void readiness.refetch()}>{uiText("重新检查配置")}</button>
      </section>
      {readiness.data && !readiness.data.ready ? (
        <div className={styles.readiness}>
          <p>{uiText("当前缓存的运行检查未通过：")}{blockingMessages.join("；")}</p>
          {topologyDiagnostics.length > 0 ? (
            <p>
              {uiText("点击“运行”会立即使用后端实时状态重新检查；检查通过后会继续创建 Run。 如仍失败，上方错误代码可用于定位，无需在画布中添加流程控制组件。")}</p>
          ) : null}
        </div>
      ) : null}
      {readiness.isError ? (
        <p className={styles.error}>{uiText("无法验证当前 revision 的运行就绪度。")}</p>
      ) : null}
      {createRun.error ? (
        <p className={styles.error}>
          {uiText("Run 创建失败：")}{createRun.error.message}{uiText("。未修改的 task 可直接安全重试。")}</p>
      ) : null}
    </form>
  );
}

/**
 * Render the persisted task and cooperative controls until authoritative terminal.
 * @param props The exact server-owned Run resource.
 * @returns Task/lifecycle facts; terminal Runs have no pending-cancel control.
 */
export function ActiveRunBar({ run }: { run: StudioRunResource }) {
  useUiLocale();
  const cancel = useCancelStudioRun();
  const canCancel = run.lifecycle !== "terminal";

  /** Request the existing cooperative cancel command after an explicit warning. */
  const requestCancel = () => {
    if (
      !canCancel
      || !window.confirm(uiText("请求协作式取消？活动中的模型或设备调用可能要返回后才会停止。"))
    ) return;
    cancel.mutate(run.runId);
  };

  return (
    <section className={styles.active} aria-label="Active Run Task">
      <div>
        <span>{uiText("当前 Task")}</span>
        <strong>{run.task.text}</strong>
      </div>
      <span className={styles.lifecycle} data-state={run.lifecycle}>{run.lifecycle}</span>
      {canCancel ? <button
        type="button"
        disabled={!canCancel || cancel.isPending || run.cancellationRequested}
        onClick={requestCancel}
      >
        {run.cancellationRequested || run.lifecycle === "cancelling" ? "Cancelling…" : "Cancel"}
      </button> : null}
      {cancel.error ? <p className={styles.error}>{uiText("取消请求失败：")}{cancel.error.message}</p> : null}
    </section>
  );
}
