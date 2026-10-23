import { uiText } from "@/shared/i18n";
import type { PhoneFrameProjection } from "@/entities/run";

export type DevicePaneStateKind =
  | "not_started"
  | "not_configured"
  | "preparing"
  | "waiting"
  | "available"
  | "stale"
  | "early_failure"
  | "offline"
  | "unauthorized"
  | "artifact_missing"
  | "artifact_corrupt";

export type DevicePaneState = {
  kind: DevicePaneStateKind;
  label: string;
  title: string;
  detail: string;
  tone: "neutral" | "warning" | "danger" | "success";
};

export type DevicePaneFacts = {
  hasRun: boolean;
  readinessReady?: boolean;
  lifecycle?: string;
  errorCode?: string;
  frameState: PhoneFrameProjection["state"];
  hasObservation: boolean;
  replayPrefix?: boolean;
};

const AUTHORITATIVE_OFFLINE = new Set([
  "studio.device.target_offline",
  "runtime.device.offline",
]);
const AUTHORITATIVE_UNAUTHORIZED = new Set([
  "studio.device.target_unauthorized",
  "runtime.device.unauthorized",
]);

/**
 * Derive Phone state without inferring offline or whole-Run absence from a prefix.
 * @param facts Authoritative lifecycle and current causal-frame visibility.
 * @returns Presentation state distinguishing partial Replay from early termination.
 */
export function selectDevicePaneState(facts: DevicePaneFacts): DevicePaneState {
  if (AUTHORITATIVE_OFFLINE.has(facts.errorCode ?? "")) {
    return {
      kind: "offline",
      label: "DEVICE OFFLINE",
      title: uiText("设备已离线"),
      detail: uiText("运行边界返回了明确的 offline 状态；当前没有可用设备截图。"),
      tone: "danger",
    };
  }
  if (AUTHORITATIVE_UNAUTHORIZED.has(facts.errorCode ?? "")) {
    return {
      kind: "unauthorized",
      label: "DEVICE UNAUTHORIZED",
      title: uiText("设备未授权"),
      detail: uiText("运行边界返回了明确的 unauthorized 状态；请在设备侧确认授权。"),
      tone: "danger",
    };
  }
  if (facts.frameState === "available") {
    return { kind: "available", label: "CURRENT EVIDENCE", title: facts.lifecycle === "terminal" && !facts.replayPrefix ? uiText("最终记录截图") : uiText("当前截图"), detail: uiText("展示已记录观察的截图，不代表设备此刻的实时画面。"), tone: "success" };
  }
  if (facts.frameState === "stale") {
    return { kind: "stale", label: "STALE EVIDENCE", title: uiText("历史截图"), detail: uiText("正在等待当前交互证据；此画面明确标记为历史截图。"), tone: "warning" };
  }
  if (facts.frameState === "missing") {
    return { kind: "artifact_missing", label: "EVIDENCE MISSING", title: uiText("当前截图缺失"), detail: uiText("持久化记录引用的截图文件不存在，不能推断设备在线状态。"), tone: "danger" };
  }
  if (facts.frameState === "corrupt") {
    return { kind: "artifact_corrupt", label: "EVIDENCE CORRUPT", title: uiText("截图证据损坏"), detail: uiText("截图完整性校验或读取失败，不能用其他画面替代。"), tone: "danger" };
  }
  if (!facts.hasRun) {
    return facts.readinessReady === false
      ? { kind: "not_configured", label: "RUN BLOCKED", title: uiText("运行环境未就绪"), detail: uiText("请先处理当前 revision 的 SecretRef、Provider 或 Device Profile 配置。"), tone: "warning" }
      : { kind: "not_started", label: "NOT STARTED", title: uiText("尚未开始运行"), detail: uiText("提交底部 Task 后才会创建 Run 并尝试采集设备证据。"), tone: "neutral" };
  }
  if (["accepted", "starting"].includes(facts.lifecycle ?? "")) {
    return { kind: "preparing", label: "PREPARING", title: uiText("正在准备运行"), detail: uiText("服务正在绑定组件并准备设备边界，尚未产生截图证据。"), tone: "neutral" };
  }
  if (facts.replayPrefix && !facts.hasObservation) {
    return { kind: "waiting", label: "NO EVIDENCE AT CURSOR", title: uiText("当前回放位置尚无截图"), detail: uiText("当前回放位置尚未出现 observation；继续回放查看后续已记录的证据。"), tone: "neutral" };
  }
  if (facts.lifecycle === "terminal" && !facts.hasObservation) {
    return { kind: "early_failure", label: "NO DEVICE EVIDENCE", title: uiText("设备证据未采集"), detail: uiText("运行在首个 observation 之前结束；这不等同于设备离线。"), tone: "warning" };
  }
  return { kind: "waiting", label: "WAITING FOR EVIDENCE", title: uiText("等待设备截图"), detail: uiText("Run 已存在，但当前尚未收到可验证的 observation 截图。"), tone: "neutral" };
}
