// 뼈대 단계의 빈 화면. 레인이 화면을 만들면 그 경로에서 빠진다.
export function Pending({ screen }: { screen: string }) {
  return <p>준비 중: {screen}</p>;
}
