import { describe, expect, it } from 'vitest';
import {
  emptyGroupMessage,
  GROUPS,
  scoreTone,
  visibleFindings,
  type ComparedFinding,
} from './view';

const item = (severity: ComparedFinding['severity'], ruleId: string): ComparedFinding => ({
  ruleId,
  severity,
  path: 'assets/index.js',
  value: '****',
  severityChanged: false,
});

describe('SCR-05 전후 비교', () => {
  it('점수 색: 오르면 up, 내리면 down, 같으면 same (05-02, F-C02 예시 58 → 78)', () => {
    expect(scoreTone(20)).toBe('up');
    expect(scoreTone(-12)).toBe('down');
    expect(scoreTone(0)).toBe('same');
  });

  it('정보는 기본으로 숨기고 켜면 서버 차례대로 보인다 (F-C02 5)', () => {
    const items = [item('high', 'S01-AWS'), item('info', 'S03-LOCAL'), item('low', 'S03-DEVHOST')];
    expect(visibleFindings(items, false).map((f) => f.ruleId)).toEqual(['S01-AWS', 'S03-DEVHOST']);
    expect(visibleFindings(items, true).map((f) => f.ruleId)).toEqual([
      'S01-AWS',
      'S03-LOCAL',
      'S03-DEVHOST',
    ]);
  });

  it('빈 묶음은 없습니다, 정보만 있는 묶음도 정보 보기가 꺼져 있으면 없습니다 (05-04)', () => {
    expect(emptyGroupMessage(visibleFindings([], false))).toBe('없습니다');
    const infoOnly = [item('info', 'S03-LOCAL')];
    expect(emptyGroupMessage(visibleFindings(infoOnly, false))).toBe('없습니다');
    expect(emptyGroupMessage(visibleFindings(infoOnly, true))).toBeNull();
  });

  it('묶음 탭은 고쳐짐 → 남음 → 새로 생김, 기본은 고쳐짐 (05-03)', () => {
    expect(GROUPS.map((g) => g.label)).toEqual(['고쳐짐', '남음', '새로 생김']);
  });
});
