import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'ZhiXing',
  tagline: 'Compose, run, and evaluate Mobile Agents',
  future: {v4: true},
  url: 'https://apbocldueo.github.io',
  baseUrl: '/unimobile/',
  organizationName: 'apbocldueo',
  projectName: 'unimobile',
  onBrokenLinks: 'throw',
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'zh-CN'],
    localeConfigs: {
      en: {label: 'English', htmlLang: 'en'},
      'zh-CN': {label: '\u7b80\u4f53\u4e2d\u6587', htmlLang: 'zh-CN'},
    },
  },
  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          editUrl:
            'https://github.com/apbocldueo/unimobile/tree/release-v2/website/',
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    colorMode: {respectPrefersColorScheme: true},
    navbar: {
      title: 'ZhiXing',
      items: [
        {type: 'docSidebar', sidebarId: 'docsSidebar', position: 'left', label: 'Documentation'},
        {type: 'localeDropdown', position: 'right'},
        {href: 'https://github.com/apbocldueo/unimobile', label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {label: 'Get started', to: '/'},
            {label: 'Tutorials', to: '/tutorials/build-an-agentgraph'},
            {label: 'Concepts', to: '/concepts/architecture'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'GitHub', href: 'https://github.com/apbocldueo/unimobile'},
            {label: 'Contributing', href: 'https://github.com/apbocldueo/unimobile/blob/release-v2/CONTRIBUTING.md'},
            {label: 'Security', href: 'https://github.com/apbocldueo/unimobile/blob/release-v2/SECURITY.md'},
          ],
        },
      ],
      copyright: `Copyright \u00a9 ${new Date().getFullYear()} ZhiXing contributors. Built with Docusaurus.`,
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula},
  } satisfies Preset.ThemeConfig,
};

export default config;
