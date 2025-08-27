import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettierPlugin from 'eslint-plugin-prettier';
import prettierConfig from 'eslint-config-prettier';

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  prettierConfig,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
    },
    rules: {
      'no-console': 'off',
      '@typescript-eslint/explicit-function-return-type': 'off', // warnからoffに変更
      '@typescript-eslint/no-explicit-any': 'off', // errorからoffに変更
      'prettier/prettier': 'error',
    },
    plugins: {
      prettier: prettierPlugin,
    },
    ignores: [
      '.venv/**',
      'node_modules/**',
      'dist/**',
      'build/**',
      'src/**/*.js',
      '**/*.test.ts',
      '**/emscripten_fetch_worker.js',
      '**/add.js',
      '**/add.ts',
    ],
  }
);
