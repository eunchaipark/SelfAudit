import { describe, expect, it } from 'vitest';
import { formatCount, formatDateTime, formatScoreChange, SEVERITY_LABEL } from './format';

describe('format', () => {
  it('UTC 시각을 한국 시각으로 보인다 (SCR-01 예: 2026-11-18 14:05)', () => {
    expect(formatDateTime('2026-11-18T05:05:00Z')).toBe('2026-11-18 14:05');
  });

  it('점수가 없으면 - (F-P02 3)', () => {
    expect(formatCount(null)).toBe('-');
    expect(formatCount(78)).toBe('78');
  });

  it('점수 변화 +n, 0, −n (F-C02 4)', () => {
    expect(formatScoreChange(20)).toBe('+20');
    expect(formatScoreChange(0)).toBe('0');
    expect(formatScoreChange(-8)).toBe('−8');
  });

  it('심각도 이름', () => {
    expect(SEVERITY_LABEL.high).toBe('높음');
  });
});
