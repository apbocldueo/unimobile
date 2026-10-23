import { uiText, useUiLocale } from "@/shared/i18n";
import { useBuilderGuide } from "../model/useBuilderGuide";
import type { BuilderGuideProgress } from "../model/builderGuideProgress";
import styles from "./agentBuilder.module.css";

type BuilderGuideProps = {
  hasCapabilities: boolean;
  hasRelations: boolean;
  hasSelection: boolean;
  progress?: Partial<BuilderGuideProgress>;
};

/** Render dismissible guidance without covering populated drafts by default.
 * Args: graph facts and optional progress determine guidance, never execution status.
 * Returns: A guide or its reopen button, respecting explicit user preference.
 */
export function BuilderGuide({ hasCapabilities, hasRelations, hasSelection, progress = {} }: BuilderGuideProps) {
  useUiLocale();
  const guide = useBuilderGuide(hasCapabilities);
  const hasPerception = progress.hasPerception ?? false;
  const hasReasoning = progress.hasReasoning ?? false;
  const hasMemory = progress.hasMemory ?? false;
  const hasActionExecutor = progress.hasActionExecutor ?? false;
  const hasInputTask = progress.hasInputTask ?? false;
  const hasInputMemory = progress.hasInputMemory ?? false;
  const hasMemoryToReasoning = progress.hasMemoryToReasoning ?? false;
  const hasPerceptionToReasoning = progress.hasPerceptionToReasoning ?? false;
  const hasReasoningToAction = progress.hasReasoningToAction ?? false;
  const hasActionToOutput = progress.hasActionToOutput ?? false;
  const hasActionFeedback = progress.hasActionFeedback ?? false;
  const contextHint = hasSelection
    ? uiText("已选中对象：右侧配置区 会显示对应配置。")
    : !hasCapabilities
      ? uiText("点击“添加能力”，依次添加 Perception、Memory、Reasoning、Action Executor，先搭出可运行的观察—记忆—决策—执行闭环。")
      : !hasPerception || !hasReasoning
        ? uiText("先补齐 Perception 和 Reasoning；Perception 负责读取画面，Reasoning 负责决定动作。")
        : !hasMemory
          ? uiText("再添加 Memory。运行时需要它保存动作结果，决定是否进入下一轮。")
          : !hasActionExecutor
            ? uiText("请添加 Action Executor。Reasoning 不能直接结束 Agent，动作执行器才可以连接 Output。")
          : !hasInputTask
            ? uiText("把 Input 的 task 输出连到 Reasoning 的 task 输入。")
            : !hasInputMemory
              ? uiText("把 Input 的 task 输出也连到 Memory 的 write 输入，让任务进入记忆。")
              : !hasPerceptionToReasoning
                ? uiText("把 Perception 的 perception 输出连到 Reasoning 的 perception 输入。设备 observation 由运行时自动提供，不要手动连 Input。")
                : !hasMemoryToReasoning
                  ? uiText("把 Memory 的 context 输出连到 Reasoning 的 memory 输入。")
                : !hasReasoningToAction
                  ? uiText("把 Reasoning 的 action 输出连到 Action Executor 的 action 输入。")
                  : !hasActionFeedback
                    ? uiText("点击 Action Executor 的“执行结果”圆点，在本次连线中选择“下一轮反馈”，再点击 Memory 的“写入记忆”；这一步让非终止动作重新观察设备。")
                : !hasActionToOutput
                  ? uiText("把 Action Executor 的 result 输出连到 Output，完成最小闭环。")
                  : hasRelations
                    ? uiText("最小闭环已连好：配置模型和 SecretRef 后点击 检查流程。")
                    : uiText("已有能力节点，下一步把输出端口连到输入端口。");

  if (!guide.visible) {
    return (
      <button type="button" className={`${styles.button} ${styles.canvasGuideToggle}`} onClick={guide.reopen}>
        {uiText("画布提示")}</button>
    );
  }

  return (
    <section className={styles.builderGuide} aria-label={uiText("画布操作引导")}>
      <div className={styles.builderGuideHeader}>
        <div>
          <span className={styles.builderGuideEyebrow}>{uiText("开始搭建")}</span>
          <strong>{uiText("先搭结构，再配置")}</strong>
        </div>
        <button type="button" className={styles.builderGuideClose} onClick={guide.dismiss} aria-label={uiText("隐藏画布提示")}>
          {uiText("隐藏")}</button>
      </div>
      <ol className={styles.builderGuideSteps}>
        <li><span>1</span><div><strong>{uiText("添加能力")}</strong><small>Perception → Memory → Reasoning → Action Executor</small></div></li>
        <li><span>2</span><div><strong>{uiText("连出执行闭环")}</strong><small>Input → Memory/Reasoning → Action Executor → Output</small></div></li>
        <li><span>3</span><div><strong>{uiText("配置并校验")}</strong><small>{uiText("选中 Reasoning 配置模型和 SecretRef，再点 检查流程")}</small></div></li>
      </ol>
      <p className={styles.builderGuideNote}>{uiText("Perception 和 Action Executor 的设备 observation 由运行时注入，不需要在画布上手动连。")}</p>
      <p className={styles.builderGuideHint} role="status">{contextHint}</p>
      <p className={styles.builderGuideFooter}>{uiText("检查流程 通过后，再点击 保存 保存。")}</p>
    </section>
  );
}
