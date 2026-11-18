import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'src/api/schema.d.ts'] },
  {
    files: ['**/*.{ts,tsx,js}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML 금지: 분석 대상의 글은 글자로만 넣는다 (보안규칙 5장)',
        },
        {
          selector: 'AssignmentExpression[left.property.name=/^(innerHTML|outerHTML)$/]',
          message: 'innerHTML 금지 (보안규칙 5장)',
        },
      ],
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'API는 src/api/client.ts로만 부른다 (외부 요청 금지, NFR-01)' },
      ],
    },
  },
  {
    files: ['src/api/client.ts'],
    rules: { 'no-restricted-globals': 'off' },
  },
);
