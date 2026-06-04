import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import importX from 'eslint-plugin-import-x'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  // Layer boundaries — mirrors the mobile module dependency direction:
  // ui/hooks → model ← api; everything may import core/; core/ never
  // imports features/ or the app shell.
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'import-x': importX },
    settings: {
      'import-x/resolver': { typescript: true },
    },
    rules: {
      'import-x/no-restricted-paths': [
        'error',
        {
          basePath: '.',
          zones: [
            {
              target: './src/core',
              from: './src/features',
              message: 'core/ must not import features/.',
            },
            {
              target: './src/core',
              from: './src/app',
              message: 'core/ must not import the app shell.',
            },
            {
              target: './src/core',
              from: './src/pages',
              message: 'core/ must not import pages/.',
            },
            {
              target: './src/features/auth/model',
              from: './src/features/auth/api',
              message: 'model/ must not import api/.',
            },
            {
              target: './src/features/auth/model',
              from: './src/features/auth/hooks',
              message: 'model/ must not import hooks/.',
            },
            {
              target: './src/features/auth/model',
              from: './src/features/auth/ui',
              message: 'model/ must not import ui/.',
            },
            {
              target: './src/features/auth/api',
              from: './src/features/auth/hooks',
              message: 'api/ must not import hooks/.',
            },
            {
              target: './src/features/auth/api',
              from: './src/features/auth/ui',
              message: 'api/ must not import ui/.',
            },
          ],
        },
      ],
    },
  },
  // shadcn/ui generated primitives export cva variants alongside their
  // components; fast-refresh purity doesn't apply to them.
  {
    files: ['src/core/ui/**/*.tsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  // Context providers conventionally co-export their hook + types.
  {
    files: ['src/core/auth/AuthContext.tsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  // model/ is pure domain logic — keep React out of it. api/ stays
  // React-free too, except mutations.ts (the TanStack Query glue).
  {
    files: ['src/features/*/model/**/*.ts', 'src/features/*/api/**/*.ts'],
    ignores: ['src/features/*/api/mutations.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            { name: 'react', message: 'model/ and api/ must stay React-free.' },
            { name: 'react-dom', message: 'model/ and api/ must stay React-free.' },
            {
              name: '@tanstack/react-query',
              message: 'TanStack Query belongs in api/mutations.ts only.',
            },
          ],
        },
      ],
    },
  },
])
