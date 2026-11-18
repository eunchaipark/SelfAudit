// 숫자·날짜·심각도 표시는 여기서만 한다 (코드규칙 5.1).
import type { Schemas } from '../api/client';

type Severity = Schemas['FindingOut']['severity'];

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const EMPTY = '-';
const MINUS = '−'; // 명세의 점수 변화 표기 (U+2212)

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: '높음',
  medium: '중간',
  low: '낮음',
  info: '정보',
};

/** ISO 시각 → `2026-11-18 14:05` (한국 시각). */
export function formatDateTime(iso: string): string {
  const kst = new Date(new Date(iso).getTime() + KST_OFFSET_MS);
  const pad = (n: number) => String(n).padStart(2, '0');
  const date = `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())}`;
  return `${date} ${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}`;
}

/** 점수나 개수가 없으면 `-`. */
export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? EMPTY : String(value);
}

/** 점수 변화: `+20`, `0`, `−8` (F-C02 4). */
export function formatScoreChange(change: number): string {
  if (change > 0) return `+${change}`;
  if (change < 0) return `${MINUS}${Math.abs(change)}`;
  return '0';
}
