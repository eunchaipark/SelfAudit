// 화면 경로표 (설계). 레인은 자기 화면을 만들면 Pending 자리를 바꾸도록 요청한다.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router';
import { Pending } from '../components/Pending';
import { RegisterPage } from '../features/apps/RegisterPage';
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
            <Route index element={<Pending screen="SCR-01 앱 목록" />} />
            <Route path="apps/new" element={<RegisterPage />} />
            <Route path="apps/:appId" element={<Pending screen="SCR-03 앱 상세" />} />
            <Route path="scans/:scanId" element={<Pending screen="SCR-04 점검 결과" />} />
            <Route path="compare" element={<Pending screen="SCR-05 전후 비교" />} />
            <Route path="*" element={<Pending screen="없는 화면" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
