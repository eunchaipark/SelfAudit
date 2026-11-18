import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

const NETWORK_MSG = 'API는 src/api/client.ts의 api()로만 부른다 (외부 요청 금지, NFR-01)';
const HTML_MSG = 'HTML 삽입 금지: 분석 대상의 글은 글자로만 넣는다 (보안규칙 5장)';

// 네트워크로 나가는 다른 길. fetch는 client.ts에서만 풀어 준다
const otherNetworkGlobals = ['XMLHttpRequest', 'WebSocket', 'EventSource'].map((name) => ({
  name,
  message: NETWORK_MSG,
}));
const fetchGlobal = { name: 'fetch', message: NETWORK_MSG };
const restrictedProperties = [
  ...['window', 'globalThis', 'self'].map((object) => ({
    object,
    property: 'fetch',
    message: NETWORK_MSG,
  })),
  { object: 'navigator', property: 'sendBeacon', message: NETWORK_MSG },
  { object: 'document', property: 'write', message: HTML_MSG },
  { object: 'document', property: 'writeln', message: HTML_MSG },
];

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
        { selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']", message: HTML_MSG },
        {
          selector: 'AssignmentExpression[left.property.name=/^(innerHTML|outerHTML)$/]',
          message: HTML_MSG,
        },
        {
          selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
          message: HTML_MSG,
        },
        {
          selector: 'Literal[value=/^\\s*javascript:/i]',
          message: 'javascript 스킴 주소 금지 (보안규칙 5장)',
        },
        {
          selector: 'TemplateElement[value.raw=/^\\s*javascript:/i]',
          message: 'javascript 스킴 주소 금지 (보안규칙 5장)',
        },
      ],
      'no-restricted-globals': ['error', fetchGlobal, ...otherNetworkGlobals],
      'no-restricted-properties': ['error', ...restrictedProperties],
    },
  },
  {
    files: ['src/api/client.ts'],
    rules: { 'no-restricted-globals': ['error', ...otherNetworkGlobals] },
  },
);
