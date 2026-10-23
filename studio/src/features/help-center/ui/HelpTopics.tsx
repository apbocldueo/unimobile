import { Link, useSearchParams } from "react-router-dom";
import { helpTopic, helpTopics, type HelpLocale, type HelpTopicId } from "../model/helpTopics";
import { documentationLink } from "../model/documentationLinks";
import { useUiLocale, useUiLocaleStore } from "@/shared/i18n";

/** Render task-specific bilingual instructions without issuing runtime requests. */
export function HelpTopics() {
  const uiLocale = useUiLocale();
  const [params, setParams] = useSearchParams();
  const requestedLocale = params.get("lang");
  const locale: HelpLocale = requestedLocale === "en" || requestedLocale === "zh-CN" ? requestedLocale : uiLocale;
  const topic = helpTopic(params.get("topic"));
  const copy = helpTopics[topic][locale];
  const article = documentationLink(topic, locale);
  /** Change only the current help topic/locale, without persisting user content. */
  const navigate = (nextTopic: HelpTopicId, nextLocale: HelpLocale) => {
    useUiLocaleStore.getState().setLocale(nextLocale);
    setParams({ topic: nextTopic, lang: nextLocale });
  };
  return <div className="mx-auto w-full max-w-4xl space-y-6">
    <header className="flex flex-wrap items-center justify-between gap-4">
      <h1 className="zx-title">{locale === "en" ? "Studio help" : "Studio 使用帮助"}</h1>
      <label>{locale === "en" ? "Language" : "语言"} <select aria-label="Help language" className="zx-control" value={locale} onChange={(event) => navigate(topic, event.target.value as HelpLocale)}><option value="en">English</option><option value="zh-CN">简体中文</option></select></label>
    </header>
    <nav aria-label="Help topics" className="flex flex-wrap gap-3">
      {(Object.keys(helpTopics) as HelpTopicId[]).map((id) => <button key={id} type="button" aria-current={topic === id ? "page" : undefined} className="zx-control px-3 py-2" onClick={() => navigate(id, locale)}>{helpTopics[id][locale].title}</button>)}
    </nav>
    <article lang={locale} className="space-y-4 rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-panel)] p-6">
      <h2 className="text-xl font-semibold text-[color:var(--zx-text-title)]">{copy.title}</h2>
      <ol className="list-decimal space-y-4 pl-5 text-sm leading-relaxed">{copy.steps.map((step) => <li key={step}>{step}</li>)}</ol>
      <p className="border-t border-[var(--zx-border-light)] pt-4 text-sm text-[color:var(--zx-text-muted)]">{copy.boundary}</p>
      <p className="text-sm"><a href={article.href} target="_blank" rel="noopener noreferrer">{article.label} ↗</a></p>
      <p className="text-sm text-[color:var(--zx-text-muted)]">{locale === "en" ? "The published article is supplementary and may show an earlier Studio version. Follow the local instructions above for this checkout." : "已发布文章作为补充参考，截图可能来自较早的 Studio 版本；当前代码请以上述本地说明为准。"}</p>
    </article>
    <div className="flex gap-4"><Link to="/agents?create=example">{locale === "en" ? "Open examples" : "打开示例"}</Link><Link to="/settings">{locale === "en" ? "Open Settings" : "打开设置"}</Link><Link to="/benchmarks">{locale === "en" ? "Open Benchmarks" : "打开 Benchmarks"}</Link></div>
  </div>;
}
