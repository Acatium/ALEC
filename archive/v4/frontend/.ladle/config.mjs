/** @type {import('@ladle/react').UserConfig} */
export default {
  stories: 'src/**/*.stories.{js,jsx,ts,tsx}',
  viteConfig: '.ladle/vite.config.mjs',
  addons: {
    theme: {
      enabled: true,
      defaultState: 'light',
    },
    mode: {
      enabled: true,
      defaultState: 'full',
    },
  },
};
