// 영수증 올리기 화면. 주 번들(index.js)이 영수증 화면을 열 때 읽는다.
// 영수증 서버를 바로 부르던 때 쓰던 서비스 토큰(지금은 /api/receipts 프록시가 붙인다):
// Authorization: Bearer {{v:H1-08}}
// verboseOcr: true 로 두면 OCR 원문을 콘솔에 찍는다.

const MAX_BYTES = 5 * 1024 * 1024;

export function mountReceipts(root, api) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/png,image/jpeg";
  const status = document.createElement("p");
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file || file.size > MAX_BYTES) {
      status.textContent = "5MB 아래 사진만 올릴 수 있습니다";
      return;
    }
    const body = new FormData();
    body.append("receipt", file);
    const result = await api("/receipts", { method: "POST", body });
    status.textContent = "올림: " + result.id;
  });
  root.append(input, status);
}
