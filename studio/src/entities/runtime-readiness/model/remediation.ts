import { uiText } from "@/shared/i18n";
import type { RuntimeEnvironmentReadiness, RuntimeReadinessDiagnostic } from "./runtimeReadiness.schema";

/** Describe static configuration without inferring device/model connectivity.
 * Args: data is the authoritative process DTO; errors take priority over cached data.
 * Returns: A short actionable status; does not change execution eligibility.
 */
export function runtimeConfigurationLabel(data: RuntimeEnvironmentReadiness | undefined, isError: boolean, isFetching: boolean): string {
  if (isError) return uiText("无法读取运行配置");
  if (isFetching || !data) return uiText("正在检查运行配置…");
  if (data.ready) return uiText("运行配置已就绪");
  if (data.diagnostics.some((item) => item.code === "studio.readiness.profile_empty")) return uiText("未加载设备配置");
  if (data.diagnostics.some((item) => item.category === "secret")) return uiText("模型密钥配置缺失");
  if (data.diagnostics.some((item) => item.category === "component")) return uiText("运行组件不可用");
  return uiText("运行配置需要处理");
}

/** Translate trusted keys to bounded instructions; unknown keys never execute.
 * Args: diagnostic is the strict safe readiness DTO.
 * Returns: Plain guidance and a preparation category, without commands or URLs.
 */
export function readinessRemediation(diagnostic: RuntimeReadinessDiagnostic): { instruction: string; preparation: "model" | "device" | "validation" | "run" } {
  switch (diagnostic.remediationKey) {
    case "configure-studio-secrets":
      return { instruction: uiText("在服务端本地密钥文件中配置所需项，重启 Studio 后刷新。密钥配置已加载不代表模型接口连接成功。"), preparation: "model" };
    case "install-provider-dependency":
      return { instruction: "Ask the server operator to install the selected provider's required dependency in the Studio environment, restart, and refresh. No installation is performed here.", preparation: "model" };
    case "configure-device-profile":
      return { instruction: uiText("后端尚未加载设备配置；手机或模拟器开着也不能替代这一步。加载本地设备配置并重启 Studio，运行时选择该设备。"), preparation: "device" };
    case "configure-component-dependency":
    case "select-available-component":
    case "select-available-dependency":
    case "save-valid-agent-revision":
      return { instruction: "Return to the Builder, review the implementation and dependencies, validate and save a new revision before checking again.", preparation: "validation" };
    default:
      return { instruction: "Review the diagnostic details and the saved revision's preparation requirements. No automatic repair is available for this diagnostic.", preparation: "run" };
  }
}
