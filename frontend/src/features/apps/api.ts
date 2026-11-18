// 앱 영역의 데이터 훅. 서버 상태는 이 훅으로만 가져온다.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, type Schemas } from '../../api/client';

export const appsKey = ['apps'] as const;

/** F-P01 앱 등록. */
export function useCreateApp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas['AppIn']) =>
      api<Schemas['AppOut']>('/api/v1/apps', { method: 'POST', json: body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: appsKey }),
  });
}
