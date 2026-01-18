import type { StorybookConfig } from '@storybook/react-vite';
import { fileURLToPath, URL } from 'node:url';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-links', '@storybook/addon-essentials'],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  docs: {
    autodocs: 'tag',
  },
  viteFinal: async (baseConfig) => {
    baseConfig.resolve ??= {};
    baseConfig.resolve.alias = {
      ...(baseConfig.resolve.alias ?? {}),
      '@shared': fileURLToPath(new URL('../src/shared', import.meta.url)),
      '@uikit': fileURLToPath(new URL('../src/uikit', import.meta.url)),
    };
    return baseConfig;
  },
};

export default config;
