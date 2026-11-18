// SCR-02 앱 등록 (F-P01). 본보기 화면: 문구는 화면정의 그대로, 판정은 서버가 한다.
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { ApiError, type Schemas } from '../../api/client';
import { FieldError } from '../../components/FieldError';
import { useCreateApp } from './api';
import styles from './RegisterPage.module.css';

type Kind = Schemas['AppIn']['kind'];
const NETWORK_ERROR = '서버 오류가 났습니다';

export function RegisterPage() {
  const navigate = useNavigate();
  const createApp = useCreateApp();
  const [name, setName] = useState('');
  const [kind, setKind] = useState<Kind>('mine');
  const [sourceUrl, setSourceUrl] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const body = { name, kind, consent, sourceUrl: kind === 'practice' ? sourceUrl : null };
    createApp.mutate(body, {
      onSuccess: (app) => navigate(`/apps/${app.id}`),
      onError: (err) => setError(err instanceof ApiError ? err.message : NETWORK_ERROR),
    });
  };

  return (
    <form className={styles.form} onSubmit={onSubmit}>
      <h1 className={styles.title}>앱 등록</h1>
      <div className={styles.row}>
        <label htmlFor="app-name">앱 이름</label>
        <input id="app-name" value={name} onChange={(e) => setName(e.target.value)} />
        <span className={styles.help}>40자까지</span>
      </div>
      <fieldset className={styles.row}>
        <legend>종류</legend>
        <label>
          <input
            type="radio"
            name="kind"
            checked={kind === 'mine'}
            onChange={() => setKind('mine')}
          />
          내 앱
        </label>
        <label>
          <input
            type="radio"
            name="kind"
            checked={kind === 'practice'}
            onChange={() => setKind('practice')}
          />
          공개 연습앱
        </label>
      </fieldset>
      {kind === 'practice' && (
        <div className={styles.row}>
          <label htmlFor="app-source">출처 주소</label>
          <input
            id="app-source"
            type="url"
            placeholder="https://"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
          />
        </div>
      )}
      <label className={styles.consent}>
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />이
        앱은 내가 직접 만들었거나, 분석이 허용된 공개 연습용 앱입니다.
      </label>
      <FieldError message={error} />
      <div className={styles.actions}>
        <button type="button" onClick={() => navigate('/')}>
          취소
        </button>
        <button type="submit" disabled={!consent || createApp.isPending}>
          등록
        </button>
      </div>
    </form>
  );
}
