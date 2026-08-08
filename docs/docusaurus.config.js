// Docusaurus 3 — restrained editorial, no AI-slop (no purple gradient, no aurora, no glass, no rounded-2xl everywhere)
 // @ts-check

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'InsightAgent',
  tagline: 'Chat with your CSV/Excel/SQL — open source, private, fast.',
  favicon: 'img/favicon.ico',
  url: 'https://your-org.github.io',
  baseUrl: '/insightagent/',
  organizationName: 'your-org',
  projectName: 'insightagent',
  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',
  i18n: { defaultLocale: 'en', locales: ['en'] },
  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          path: '.',
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
          exclude: ['**/node_modules/**', '**/build/**'],
        },
        blog: false,
        theme: { customCss: './src/css/custom.css' },
      }),
    ],
  ],
  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: 'InsightAgent',
        items: [
          { type: 'docSidebar', sidebarId: 'docs', position: 'left', label: 'Docs' },
          { href: 'https://github.com/your-org/insightagent', label: 'GitHub', position: 'right' },
        ],
      },
      footer: {
        style: 'light',
        links: [
          { title: 'Docs', items: [{ label: 'Intro', to: '/README' }] },
          { title: 'Community', items: [{ label: 'Contributing', to: '/CONTRIBUTING' }] },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} InsightAgent — MIT`,
      },
      colorMode: { respectPrefersColorScheme: true },
      prism: { theme: require('prism-react-renderer').themes.github, darkTheme: require('prism-react-renderer').themes.dracula },
    }),
};

export default config;
