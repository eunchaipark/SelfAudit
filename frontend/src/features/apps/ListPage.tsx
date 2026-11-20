// SCR-01 앱 목록 (F-P02 4). 문구는 화면정의 그대로, 정렬과 최근 점수는 서버가 한다.
import { Link, useNavigate } from 'react-router';
import { ApiError } from '../../api/client';
import { FieldError } from '../../components/FieldError';
import { useApps } from './api';
import styles from './ListPage.module.css';
import { KIND_LABEL, latestScanText, latestScoreText, NO_APPS, type AppListItem } from './view';

const NETWORK_ERROR = '서버 오류가 났습니다';

export function AppListPage() {
  const apps = useApps();

  return (
    <section className={styles.page}>
      <div className={styles.actions}>
        <Link to="/apps/new" className={styles.register}>
          + 앱 등록
        </Link>
      </div>
      <AppListBody
        items={apps.data}
        error={apps.isError ? apps.error : null}
        loading={apps.isPending}
      />
    </section>
  );
}

function AppListBody({
  items,
  error,
  loading,
}: {
  items: AppListItem[] | undefined;
  error: Error | null;
  loading: boolean;
}) {
  if (error) {
    return <FieldError message={error instanceof ApiError ? error.message : NETWORK_ERROR} />;
  }
  if (loading || !items) {
    return <div aria-busy="true" />;
  }
  if (items.length === 0) {
    return <p className={styles.empty}>{NO_APPS}</p>;
  }
  return <AppTable items={items} />;
}

function AppTable({ items }: { items: AppListItem[] }) {
  const navigate = useNavigate();
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">이름</th>
            <th scope="col">종류</th>
            <th scope="col" className={styles.number}>
              최근 점수
            </th>
            <th scope="col">최근 점검</th>
          </tr>
        </thead>
        <tbody>
          {items.map((app) => (
            <tr key={app.id} className={styles.row} onClick={() => navigate(`/apps/${app.id}`)}>
              <td>
                {/* 키보드로도 갈 수 있게 이름은 진짜 링크로 둔다. 행의 이동과 겹치지 않게 막는다 */}
                <Link
                  to={`/apps/${app.id}`}
                  className={styles.name}
                  onClick={(e) => e.stopPropagation()}
                >
                  {app.name}
                </Link>
              </td>
              <td>{KIND_LABEL[app.kind]}</td>
              <td className={styles.number}>{latestScoreText(app)}</td>
              <td>{latestScanText(app)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
