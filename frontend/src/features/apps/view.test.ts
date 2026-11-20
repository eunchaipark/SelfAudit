import { describe, expect, it } from 'vitest';
import { KIND_LABEL, latestScanText, latestScoreText, NO_SCAN_YET, type AppListItem } from './view';

const app = (over: Partial<AppListItem>): AppListItem => ({
  id: 1,
  name: 'Juice Shop',
  kind: 'practice',
  latestScore: null,
  latestScanAt: null,
  ...over,
});

describe('SCR-01 앱 목록', () => {
  it('최근 점수·시각: 완료 점검이 있으면 점수와 한국 시각 (F-P02 예시 78)', () => {
    const item = app({ latestScore: 78, latestScanAt: '2026-11-18T05:05:00Z' });
    expect(latestScoreText(item)).toBe('78');
    expect(latestScanText(item)).toBe('2026-11-18 14:05');
  });

  it('점검 0개면 최근 점수 `-`, 최근 점검 `아직 점검이 없습니다` (01-02, F-P02 예시)', () => {
    const item = app({ kind: 'mine', name: '내 블로그' });
    expect(latestScoreText(item)).toBe('-');
    expect(latestScanText(item)).toBe(NO_SCAN_YET);
    expect(NO_SCAN_YET).toBe('아직 점검이 없습니다');
  });

  it('0점도 점수로 보인다', () => {
    expect(latestScoreText(app({ latestScore: 0, latestScanAt: '2026-11-18T05:05:00Z' }))).toBe(
      '0',
    );
  });

  it('종류는 한국어로 (값의 코드)', () => {
    expect(KIND_LABEL.mine).toBe('내 앱');
    expect(KIND_LABEL.practice).toBe('공개 연습앱');
  });
});
