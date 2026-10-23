import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { useState } from "react";
import { Link } from "react-router-dom";
import builderImage from "./assets/builder.png";
import replayImage from "./assets/replay.png";
import benchmarkImage from "./assets/benchmark.png";
import builderEnglishImage from "./assets/builder.en.png";
import replayEnglishImage from "./assets/replay.en.png";
import benchmarkEnglishImage from "./assets/benchmark.en.png";
import styles from "./productHome.module.css";

const productViews = [
  {
    id: "build", /** Read this static UI label in the selected language. */ get label() { return uiText("构建 Agent"); }, caption: "AGENT BUILDER", /** Read this static UI label in the selected language. */ get title() { return uiText("把你的方法，\n搭成一个 Agent。"); },
    /** Read this static UI label in the selected language. */ get description() { return uiText("从示例出发，组合感知、推理、记忆与行动能力。调整组件与连接，让研究想法有一个可以运行的形态。"); },
    image: builderImage, englishImage: builderEnglishImage, /** Read this static UI label in the selected language. */ get alt() { return uiText("知行 Agent Builder：感知、推理、记忆与动作执行能力通过画布连接"); },
    /** Read this static UI label in the selected language. */ get note() { return uiText("Builder 示例截图 · 展示已整理的能力画布"); }, link: "/agents?create=example", /** Read this static UI label in the selected language. */ get action() { return uiText("从示例创建 Agent"); },
  },
  {
    id: "run", /** Read this static UI label in the selected language. */ get label() { return uiText("运行与回放"); }, caption: "RUN & REPLAY", /** Read this static UI label in the selected language. */ get title() { return uiText("看见每一步，\n才能继续改进。"); },
    /** Read this static UI label in the selected language. */ get description() { return uiText("在 Android 设备上运行任务，将设备截图与执行过程放在一起查看。回到记录中的任一步，检查 Agent 的观察、判断与行动。"); },
    image: replayImage, englishImage: replayEnglishImage, /** Read this static UI label in the selected language. */ get alt() { return uiText("知行 Replay：执行路径、Android 设备截图，以及循环次数耗尽的失败说明"); },
    /** Read this static UI label in the selected language. */ get note() { return uiText("历史回放截图 · 此任务未完成，展示失败后的排查入口"); }, link: "/history", /** Read this static UI label in the selected language. */ get action() { return uiText("查看运行记录"); },
  },
  {
    id: "evaluate", /** Read this static UI label in the selected language. */ get label() { return uiText("独立评测"); }, caption: "BENCHMARK", /** Read this static UI label in the selected language. */ get title() { return uiText("让任务结果，\n有据可查。"); },
    /** Read this static UI label in the selected language. */ get description() { return uiText("独立定义 Benchmark 任务与评测规则。选择已保存的 Agent 版本，确认实验配置，再通过报告、轨迹与证据检查结果。"); },
    image: benchmarkImage, englishImage: benchmarkEnglishImage, /** Read this static UI label in the selected language. */ get alt() { return uiText("知行 Benchmark Composer：任务、实验预算、设备选择与执行前的确定性预览"); },
    /** Read this static UI label in the selected language. */ get note() { return uiText("实验配置截图 · 展示执行前预览，不代表评测已通过"); }, link: "/benchmarks", /** Read this static UI label in the selected language. */ get action() { return uiText("浏览 Benchmark"); },
  },
] as const;

const journey = [
  { /** Read this static UI label in the selected language. */ get title() { return uiText("选择一个示例"); }, /** Read this static UI label in the selected language. */ get text() { return uiText("先用已有方法建立起点，再调整你关心的能力。"); }, path: "/agents?create=example", /** Read this static UI label in the selected language. */ get action() { return uiText("浏览 Agent 示例"); } },
  { /** Read this static UI label in the selected language. */ get title() { return uiText("准备模型与设备"); }, /** Read this static UI label in the selected language. */ get text() { return uiText("配置模型，连接测试用 Android 设备，完成运行检查。"); }, path: "/help?topic=device", /** Read this static UI label in the selected language. */ get action() { return uiText("阅读准备指南"); } },
  { /** Read this static UI label in the selected language. */ get title() { return uiText("运行一个小任务"); }, /** Read this static UI label in the selected language. */ get text() { return uiText("输入明确的目标，观察 Agent 如何理解画面并采取行动。"); }, path: "/help?topic=run", /** Read this static UI label in the selected language. */ get action() { return uiText("了解如何运行"); } },
  { /** Read this static UI label in the selected language. */ get title() { return uiText("回看，再改进"); }, /** Read this static UI label in the selected language. */ get text() { return uiText("检查任务结果与过程记录，修改方法，或进入独立评测。"); }, path: "/history", /** Read this static UI label in the selected language. */ get action() { return uiText("打开运行记录"); } },
] as const;

/** Render the query-free product introduction; local selection never runs an Agent. */
export function ProductHomePage() {
  const uiLocale = useUiLocale();
  const [selectedView, setSelectedView] = useState(0);
  const view = productViews[selectedView];
  const previewImage = uiLocale === "en" ? view.englishImage : view.image;

  return <div className={styles.page} id="home-top">
    <a href="#home-content" className={styles.skipLink}>{uiText("跳到主要内容")}</a>
    <header className={styles.header}>
      <a href="#home-top" className={styles.brand} aria-label={uiText("知行 ZhiXing 首页")}>
        <span className={styles.brandMark} aria-hidden="true">Z<span>↗</span></span>
        <span><span lang="zh-CN">知行</span> <span className={styles.brandEnglish}>ZhiXing</span></span>
      </a>
      <nav className={styles.navigation} aria-label={uiText("首页导航")}>
        <a href="#product">{uiText("产品能力")}</a><a href="#get-started">{uiText("使用流程")}</a><Link to="/help?topic=start">{uiText("文档与帮助")}</Link>
      </nav>
      <Link className={styles.headerAction} to="/agents">{uiText("进入知行")}{" "}<span aria-hidden="true">↗</span></Link>
    </header>

    <main id="home-content" tabIndex={-1}>
      <section className={styles.hero} aria-labelledby="home-title">
        <p className={styles.eyebrow}><span aria-hidden="true" /> {" "}{uiText("MOBILE AGENT · 从方法到行动")}</p>
        <div className={styles.heroCopy}>
          <h1 id="home-title">{uiText("构建、运行与评测")}<br />{uiText("你的")}{" "}<span>Mobile Agent.</span></h1>
          <div className={styles.heroAside}>
            <p>{uiText("让想法在手机上行动。")}<br />{uiText("让每一步，都有迹可循。")}</p>
            <p className={styles.heroDescription}>{uiText("面向移动智能体研究，将组件搭建、真实设备执行、过程回放与独立评测连接起来。")}</p>
            <div className={styles.actions}><Link to="/agents" className={styles.primary}>{uiText("进入知行")}{" "}<span aria-hidden="true">↗</span></Link><a href="#get-started" className={styles.textLink}>{uiText("了解使用流程")}{" "}<span aria-hidden="true">↓</span></a></div>
          </div>
        </div>
      </section>

      <section id="product" className={styles.product} aria-label={uiText("产品能力展示")}>
        <div className={styles.productBar}>
          <span className={styles.stageLabel}>ZHIXING STUDIO</span>
          <div className={styles.viewControls} role="group" aria-label={uiText("选择产品预览")}>
            {productViews.map((item, index) => <button type="button" key={item.id} aria-pressed={selectedView === index} aria-controls="product-preview" onClick={() => setSelectedView(index)}>{item.label}</button>)}
          </div>
          <span className={styles.exampleLabel}>{uiText("界面示例 · 非实时运行")}</span>
        </div>
        <div className={styles.productBody} id="product-preview" role="region" aria-label={view.label}>
          <div className={styles.productCopy}>
            <p className={styles.stageLabel}>{view.caption}</p>
            <h2>{view.title}</h2><p>{view.description}</p>
            <Link className={styles.stageLink} to={view.link}>{view.action} <span aria-hidden="true">↗</span></Link>
          </div>
          <figure className={styles.preview}>
            <a href={previewImage} target="_blank" rel="noreferrer" aria-label={uiMessage`查看${view.label}完整截图（新标签页）`}><img src={previewImage} alt={view.alt} width="1280" height="720" fetchPriority="high" /></a>
            <figcaption><span>{view.note}</span><a href={previewImage} target="_blank" rel="noreferrer">{uiText("查看大图 ↗")}<span className={styles.srOnly}>{uiText("（新标签页）")}</span></a></figcaption>
          </figure>
        </div>
      </section>

      <section className={styles.capabilities} aria-label={uiText("知行的三项核心能力")}>
        <article><p className={styles.eyebrow}>COMPOSE</p><h2>{uiText("方法，可以组合。")}</h2><p>{uiText("复用组件，替换实现，调整能力之间的关系。从已有 Agent 出发，也能构建自己的方法。")}</p></article>
        <article><p className={styles.eyebrow}>OBSERVE</p><h2>{uiText("行动，可以回看。")}</h2><p>{uiText("把设备画面、执行步骤和组件信息对应起来。保留过程记录，为调试与人工排查提供依据。")}</p></article>
        <article><p className={styles.eyebrow}>EVALUATE</p><h2>{uiText("评测，独立定义。")}</h2><p>{uiText("Agent 的做法与任务的评判标准分开维护。用独立 Benchmark 检查任务结果，留下实验报告与证据。")}</p></article>
      </section>

      <section id="get-started" className={styles.journey} aria-labelledby="journey-title">
        <div className={styles.sectionIntro}><div><p className={styles.eyebrow}>{uiText("从这里开始")}</p><h2 id="journey-title">{uiText("第一个 Agent，")}<br />{uiText("从一次小任务开始。")}</h2></div><p>{uiText("不必一开始就搭建复杂系统。")}<br />{uiText("先走通一个可观察、可回看的完整过程。")}</p></div>
        <ol className={styles.steps}>{journey.map((step, index) => <li key={step.title}><span className={styles.stepNumber}>0{index + 1}</span><h3>{step.title}</h3><p>{step.text}</p><Link className={styles.textLink} to={step.path}>{step.action} <span aria-hidden="true">↗</span></Link></li>)}</ol>
        <p className={styles.journeyNote}>{uiText("首次可以从“确认当前设置首页”开始。真实运行需要你配置模型与设备，并会产生相应的模型调用费用。")}</p>
      </section>

      <section className={styles.research} aria-labelledby="research-title">
        <div><p className={styles.eyebrow}>{uiText("为研究与开发而构建")}</p><h2 id="research-title">{uiText("从可视化搭建，")}<br />{uiText("走向你自己的方法。")}</h2><p>{uiText("Studio 是知行的可视化入口。你也可以通过 Python 与 YAML 构建 Agent，扩展组件与插件，独立编写 Benchmark 任务。")}</p><Link className={styles.textLink} to="/help?topic=start">{uiText("阅读使用指南")}{" "}<span aria-hidden="true">↗</span></Link></div>
        <div className={styles.researchPaths}>
          <Link to="/agents?create=example"><span>Agent</span><div><h3>{uiText("探索已有方法")}</h3><p>{uiText("从正式示例创建自己的 Agent")}</p></div><span aria-hidden="true">↗</span></Link>
          <Link to="/benchmark-authoring"><span>Benchmark</span><div><h3>{uiText("定义你的研究任务")}</h3><p>{uiText("独立编写任务、准备过程与评测规则")}</p></div><span aria-hidden="true">↗</span></Link>
          <Link to="/help?topic=benchmark"><span>Guide</span><div><h3>{uiText("了解实验流程")}</h3><p>{uiText("从准备、预览到报告与回放")}</p></div><span aria-hidden="true">↗</span></Link>
        </div>
      </section>

      <section className={styles.faq} aria-labelledby="faq-title">
        <h2 id="faq-title">{uiText("开始之前，你可能想知道")}</h2>
        <div>
          <details><summary>{uiText("需要先连接手机，才能使用知行吗？")}</summary><p>{uiText("浏览首页、搭建 Agent 和查看已有回放不需要连接设备。运行真实任务时，需要配置模型和 Android 设备，并通过运行前检查。")}</p></details>
          <details><summary>{uiText("运行 Agent，一定要先创建 Benchmark 吗？")}</summary><p>{uiText("不需要。可以直接给已保存的 Agent 输入任务并运行。需要独立的任务初始化与结果评判时，再使用 Benchmark 实验。")}</p></details>
          <details><summary>{uiText("首页上的画面是正在运行的任务吗？")}</summary><p>{uiText("不是。这些是知行实际界面的历史截图，用于介绍产品。回放示例展示了一次未完成任务的排查界面；实验截图展示执行前的配置预览。")}</p></details>
        </div>
      </section>

      <section className={styles.closing} aria-labelledby="closing-title"><div><p>{uiText("知 · 而后行")}</p><h2 id="closing-title">{uiText("让下一个想法，")}<br />{uiText("开始行动。")}</h2></div><Link to="/agents" className={styles.closingAction}>{uiText("进入知行")}{" "}<span aria-hidden="true">↗</span></Link></section>
    </main>

    <footer className={styles.footer}><a href="#home-top" className={styles.brand} aria-label={uiText("返回首页顶部")}>{uiText("知行")}{" "}<span className={styles.brandEnglish}>ZhiXing</span></a><p>{uiText("构建方法，观察行动，检验结果。")}</p><nav aria-label={uiText("页脚导航")}><Link to="/help?topic=start">{uiText("使用指南")}</Link><Link to="/agents">{uiText("我的 Agents ↗")}</Link></nav></footer>
  </div>;
}
