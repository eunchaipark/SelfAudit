// SCR-01 앱 목록의 표시 규칙 (순수). 점수·최근 점검을 고르는 일은 서버가 한다 (F-P02 4).
import type { Schemas } from '../../api/client';
import { formatCount, formatDateTime } from '../../lib/format';

export type AppListItem = Schemas['AppListItemOut'];
type Kind = AppListItem['kind'];

export const KIND_LABEL: Record<Kind, string> = {
  mine: '내 앱',
  practice: '공개 연습앱',
};

export const NO_SCAN_YET = '아직 점검이 없습니다';
export const NO_APPS =
  '점검할 앱을 먼저 등록하세요. 직접 만든 앱이나 분석이 허용된 연습용 앱만 등록할 수 있습니다.';

/** 01-02 `최근 점수` 칸: 완료 점검이 없으면 `-`. */
export function latestScoreText(app: AppListItem): string {
  return formatCount(app.latestScore);
}

/** 01-02 `최근 점검` 칸: 완료 점검이 없으면 `아직 점검이 없습니다`. */
export function latestScanText(app: AppListItem): string {
  return app.latestScanAt ? formatDateTime(app.latestScanAt) : NO_SCAN_YET;
}
