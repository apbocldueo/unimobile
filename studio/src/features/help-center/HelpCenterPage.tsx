/** 帮助中心占位页；侧栏入口，后续可接文档与工单。 */
export function HelpCenterPage() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto p-8">
      <h1 className="zx-title">帮助中心</h1>
      <p className="zx-body-sm mt-4 max-w-xl leading-relaxed" style={{ color: "var(--zx-text-body)" }}>
        此处将汇总 Studio 使用说明、策略与插件约定、快捷键与常见问题。当前为占位页面。
      </p>
    </div>
  );
}
