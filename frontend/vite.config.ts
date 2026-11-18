import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// 개발 서버도 127.0.0.1에만 연다 (NFR-01). /api는 서버(8790)로 넘긴다.
// changeOrigin: 서버의 Host 검사(NFR-08)를 통과하도록 Host를 127.0.0.1:8790으로 바꾼다.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8790', changeOrigin: true } },
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
  build: { sourcemap: false },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
