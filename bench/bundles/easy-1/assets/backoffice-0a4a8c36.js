// 주문 관리 화면 (직원용)
function isStaff() {
  return localStorage.getItem("pb_staff") === "1";
}

async function loadOrders() {
  const res = await fetch("/api/orders?all=1");
  return res.json();
}

export async function view() {
  const app = document.getElementById("app");
  if (!isStaff()) {
    app.textContent = "권한이 없습니다";
    return;
  }
  const orders = await loadOrders();
  app.textContent = orders.length + "건";
}
//# sourceMappingURL=backoffice-0a4a8c36.js.map
