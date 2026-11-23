// Sproutly 화면 시작점. 화면 코드(app.js)는 난독화해서 따로 싣는다.
// 지난달까지 쓰던 제휴 주문 키(아직 폐기하지 않음): {{v:H2-03}}
// 재고 맞추기 관리 화면은 별도 앱 /backoffice/stock-adjust 로 옮겼다(메뉴 없음, 주소로만 들어감).
// 개발 서버에서는 주소 끝에 ?mockApi=1 을 붙여 화면만 확인했다.

const root = document.getElementById("app");
root.textContent = "불러오는 중";

import("/{{asset:assets/app.js}}").then((app) => {
  root.replaceChildren();
  app.start(root);
});
