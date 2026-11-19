// SCR-05 전후 비교 (F-C02). 문구는 화면정의 그대로, 비교와 정렬은 서버가 한다.
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { ApiError, type Schemas } from '../../api/client';
import { FieldError } from '../../components/FieldError';
import { formatCount, formatDateTime, formatScoreChange, SEVERITY_LABEL } from '../../lib/format';
import { useComparison, useScan } from './api';
import styles from './ComparePage.module.css';
import { GROUPS, scoreTone, visibleFindings, type ComparedFinding, type GroupKey } from './view';

const NETWORK_ERROR = '서버 오류가 났습니다';
const RULES_VERSION_NOTICE = '규칙 버전이 달라 일부 차이는 규칙 때문일 수 있습니다';

export function ComparePage() {
  const [params] = useSearchParams();
  const comparison = useComparison(params.get('a') ?? '', params.get('b') ?? '');

  if (comparison.isError) {
    const err = comparison.error;
    return <FieldError message={err instanceof ApiError ? err.message : NETWORK_ERROR} />;
  }
  if (!comparison.data) {
    return <section aria-busy="true" className={styles.page} />;
  }
  return <ComparisonView data={comparison.data} />;
}

function ComparisonView({ data }: { data: Schemas['ComparisonOut'] }) {
  const [group, setGroup] = useState<GroupKey>('fixed');
  const [showInfo, setShowInfo] = useState(false);
  const appName = useScan(data.beforeId).data?.appName;
  const tone = scoreTone(data.scoreChange);
  const items = visibleFindings(data[group], showInfo);
  const groupLabel = GROUPS.find((g) => g.key === group)?.label;
  const period = `전 ${formatDateTime(data.beforeStartedAt)} → 후 ${formatDateTime(data.afterStartedAt)}`;
  const scores = `${formatCount(data.beforeScore)} → ${formatCount(data.afterScore)}`;
  const scoreLine = `점수 ${scores} (${formatScoreChange(data.scoreChange)})`;

  return (
    <section className={styles.page}>
      <h1 className={styles.title}>{appName ? `${appName} · ${period}` : period}</h1>
      <p className={`${styles.score} ${styles[tone]}`}>{scoreLine}</p>
      {data.rulesVersionDiffers && (
        <p role="note" className={styles.notice}>
          {RULES_VERSION_NOTICE}
        </p>
      )}
      <div className={styles.controls}>
        <div className={styles.tabs}>
          {GROUPS.map((g) => (
            <button
              key={g.key}
              type="button"
              aria-pressed={group === g.key}
              className={styles.tab}
              onClick={() => setGroup(g.key)}
            >
              {g.label} {formatCount(visibleFindings(data[g.key], showInfo).length)}
            </button>
          ))}
        </div>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={showInfo}
            onChange={(e) => setShowInfo(e.target.checked)}
          />
          정보 보기
        </label>
      </div>
      <h2 className={styles.groupTitle}>{groupLabel}</h2>
      <FindingList items={items} />
    </section>
  );
}

function FindingList({ items }: { items: ComparedFinding[] }) {
  if (items.length === 0) {
    return <p className={styles.empty}>없습니다</p>;
  }
  return (
    <ul className={styles.list}>
      {items.map((item, index) => (
        <li key={`${index}-${item.ruleId}-${item.path}`} className={styles.row}>
          <span className={`${styles.severity} ${styles[item.severity]}`}>
            {SEVERITY_LABEL[item.severity]}
          </span>
          <span className={styles.rule}>{item.ruleId}</span>
          <span className={styles.path}>{item.path}</span>
          <span className={styles.value}>{item.value}</span>
          {item.severityChanged && <span className={styles.changed}>심각도 바뀜</span>}
        </li>
      ))}
    </ul>
  );
}
