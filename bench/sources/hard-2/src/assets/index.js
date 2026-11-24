// Sproutly 화면 시작점. 화면 코드(app.js)는 난독화해서 따로 싣는다.
// 지난달까지 쓰던 제휴 주문 키(아직 폐기하지 않음): {{v:H2-03}}
// 재고 맞추기 관리 화면은 별도 앱 /backoffice/stock-adjust 로 옮겼다(메뉴 없음, 주소로만 들어감).

const root = document.getElementById("app");
const LOADING = "화분 목록을 불러오는 중입니다";
const RETRY = "화면을 불러오지 못했습니다. 새로 고침해 주세요";

function showLoading() {
  const spinner = document.createElement("div");
  spinner.className = "spinner";
  spinner.setAttribute("role", "status");
  spinner.textContent = LOADING;
  root.replaceChildren(spinner);
}

function showRetry() {
  const again = document.createElement("button");
  again.className = "retry";
  again.textContent = RETRY;
  again.addEventListener("click", () => location.reload());
  root.replaceChildren(again);
}

showLoading();

import("/{{asset:assets/app.js}}")
  .then((app) => {
    root.replaceChildren();
    app.start(root);
  })
  .catch(showRetry);

// 개발 서버에서는 주소 끝에 ?mockApi=1 을 붙여 화면만 확인했다.
