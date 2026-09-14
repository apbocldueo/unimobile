import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'intro',
    {
      type: 'category', label: 'Get started',
      items: ['getting-started/installation', 'getting-started/first-agent'],
    },
    {
      type: 'category', label: 'Tutorials',
      items: ['tutorials/studio-first-agent', 'tutorials/build-an-agentgraph', 'tutorials/run-on-android', 'tutorials/run-a-benchmark'],
    },
    {
      type: 'category', label: 'Concepts',
      items: [
        'concepts/architecture',
        'concepts/agentgraph',
        'concepts/benchmarking',
        'concepts/evidence-and-outcomes',
      ],
    },
    {
      type: 'category', label: 'How-to guides',
      items: [
        'guides/author-graph-yaml',
        'guides/configure-secrets',
        'guides/prepare-android',
        'guides/create-benchmark-package',
      ],
    },
    {
      type: 'category', label: 'Reference',
      items: [
        'reference/cli',
        'reference/components',
        'reference/plugins',
        'reference/source-documents',
      ],
    },
  ],
};

export default sidebars;
