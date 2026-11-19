// SCR-05 표시 규칙. 비교 계산은 서버가 하고, 여기는 보이는 방식만 정한다.
import type { Schemas } from '../../api/client';

export type ComparedFinding = Schemas['ComparedFindingOut'];
export type GroupKey = 'fixed' | 'remaining' | 'new';
export type ScoreTone = 'up' | 'down' | 'same';

/** 05-03 묶음 탭 차례와 이름. 기본은 첫 묶음 `고쳐짐`. */
export const GROUPS: readonly { key: GroupKey; label: string }[] = [
  { key: 'fixed', label: '고쳐짐' },
  { key: 'remaining', label: '남음' },
  { key: 'new', label: '새로 생김' },
];

/** 05-02 점수 색: 오르면 초록, 내리면 빨강, 같으면 회색. */
export function scoreTone(change: number): ScoreTone {
  if (change > 0) return 'up';
  if (change < 0) return 'down';
  return 'same';
}

/** F-C02 5: `정보`는 기본으로 숨기고, 정보 보기를 켜면 보인다. 서버 정렬은 그대로 둔다. */
export function visibleFindings(
  items: readonly ComparedFinding[],
  showInfo: boolean,
): ComparedFinding[] {
  return showInfo ? [...items] : items.filter((item) => item.severity !== 'info');
}
