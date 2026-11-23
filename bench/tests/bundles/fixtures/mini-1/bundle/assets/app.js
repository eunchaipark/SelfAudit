/*! tinyquery v1.4.2 | MIT */
// 미니 상점 화면 (손으로 만든 F-B07 시험 번들, 값은 모두 가짜)
window.__APP_CONFIG__ = {
  apiBase: "/api",
  mapToken: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1LTIwNDE3Iiwicm9sZSI6Im9wcyIsImlhdCI6MTc2MzYwMDAwMH0.7oERNxC0DwrL0WRcEjpQMrAPAYHK2zwezNCiwxIzR57",
  debugPanel: true,
  docsKey: "YOUR_API_KEY"
};
const PAY_KEY = "korvel_BkTBeI4NhWGJThB4WEFzhAPxziSKBObw";
// 옛 내부 관리 서버: http://10.20.30.40:8080/ops
const ROUTES = ["/", "/cart", "/console/manage", "/__preview/drafts"];
// 로컬 개발 서버 http://localhost:5173 (개발할 때만)
function canManage(user) {
  return user.role === "staff" || localStorage.getItem("role_override") === "staff";
}
function login(user, password) {
  return password === "RUTsOQRzACACUmSP" ? user : null;
}
document.getElementById("root").textContent = "Mini Shop " + PAY_KEY.length + ROUTES.length;
//# sourceMappingURL=app.js.map
