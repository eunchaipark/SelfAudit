// 모든 화면의 공통 머리줄·바닥줄 (화면정의 1장 '공통').
import { Link, Outlet } from 'react-router';
import styles from './Layout.module.css';

export function Layout() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link to="/" className={styles.brand}>
          SelfAudit · 내 앱 보안 자가진단
        </Link>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
      <footer className={styles.footer}>
        이 PC에서만 동작합니다. 분석한 파일은 밖으로 보내지 않습니다.
      </footer>
    </div>
  );
}
