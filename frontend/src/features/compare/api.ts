// 비교 영역의 데이터 훅. 서버 상태는 이 훅으로만 가져온다.
import { useQuery } from '@tanstack/react-query';
import { api, type Schemas } from '../../api/client';

/** F-C02 두 점검 비교. 전후 판단과 검증은 서버가 한다 (고른 순서 그대로 보낸다). */
export function useComparison(a: string, b: string) {
  return useQuery({
    queryKey: ['compare', a, b],
    queryFn: () => {
      const query = new URLSearchParams({ a, b });
      return api<Schemas['ComparisonOut']>(`/api/v1/compare?${query.toString()}`);
    },
  });
}

/** SCR-05 05-01 제목의 앱 이름. ComparisonOut에 앱 이름이 없어 점검 하나를 읽는다. */
export function useScan(scanId: number | undefined) {
  return useQuery({
    queryKey: ['scans', scanId],
    queryFn: () => api<Schemas['ScanOut']>(`/api/v1/scans/${scanId}`),
    enabled: scanId !== undefined,
  });
}
