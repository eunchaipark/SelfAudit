// 화면 경로표 (설계). 각 화면 파일은 그 영역 레인의 것이다 (docs/00_지도.md 레인 표).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router';
import { Pending } from '../components/Pending';
import { AppListPage } from '../features/apps/ListPage';
import { RegisterPage } from '../features/apps/RegisterPage';
import { ComparePage } from '../features/compare/ComparePage';
import { AppDetailPage } from '../features/scans/AppDetailPage';
import { ScanResultPage } from '../features/scans/ScanResultPage';
import { Layout } from './Layout';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<AppListPage />} />
            <Route path="apps/new" element={<RegisterPage />} />
            <Route path="apps/:appId" element={<AppDetailPage />} />
            <Route path="scans/:scanId" element={<ScanResultPage />} />
            <Route path="compare" element={<ComparePage />} />
            <Route path="*" element={<Pending screen="없는 화면" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
