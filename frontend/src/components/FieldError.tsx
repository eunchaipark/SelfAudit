// 입력칸 아래 오류 문구. 글은 일반 텍스트로만 넣는다.
import styles from './FieldError.module.css';

export function FieldError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className={styles.error}>
      {message}
    </p>
  );
}
