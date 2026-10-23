import type { HelpLocale, HelpTopicId } from "./helpTopics";

// Article bodies and their translations were checked against the public site.
// These links supplement local Studio instructions, not replace service setup.
const DOCUMENTS: Record<HelpTopicId, { path: string; label: Record<HelpLocale, string> }> = {
  start: { path: "tutorials/studio-first-agent/", label: { en: "Studio walkthrough", "zh-CN": "Studio 入门教程" } },
  validation: { path: "tutorials/studio-first-agent/", label: { en: "Validate and save in Studio", "zh-CN": "在 Studio 校验与保存" } },
  model: { path: "guides/configure-secrets/", label: { en: "SecretRef and CLI binding reference", "zh-CN": "SecretRef 与 CLI 绑定参考" } },
  device: { path: "guides/prepare-android/", label: { en: "Android target checks (explicit device operations)", "zh-CN": "Android 目标检查（显式设备操作）" } },
  run: { path: "tutorials/studio-first-agent/", label: { en: "Studio preparation walkthrough (not an execution result)", "zh-CN": "Studio 运行准备教程（不是执行结果）" } },
  benchmark: { path: "guides/create-benchmark-package/", label: { en: "Benchmark Package structure and validation", "zh-CN": "Benchmark Package 结构与校验" } },
};

/** Return an allowlisted public article without incorporating user/resource data.
 * Args: topic and locale are already validated UI selections.
 * Returns: A fixed HTTPS URL and a description of that article's actual scope.
 */
export function documentationLink(topic: HelpTopicId, locale: HelpLocale): { href: string; label: string } {
  const article = DOCUMENTS[topic];
  return { href: `https://apbocldueo.github.io/unimobile/${locale === "zh-CN" ? "zh-CN/" : ""}${article.path}`, label: article.label[locale] };
}
