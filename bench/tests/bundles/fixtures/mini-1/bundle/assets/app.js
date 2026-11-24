/*! tinyquery v1.4.2 | MIT */
// 미니 상점 화면 (손으로 만든 F-B07 시험 번들, 값은 모두 가짜)
window.__APP_CONFIG__ = {
  apiBase: "/api",
  mapToken: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1LTIwNDE3Iiwicm9sZSI6Im9wcyIsImlhdCI6MTc2MzYwMDAwMH0.7oERNxC0DwrL0WRcEjpQMrAPAYHK2zwezNCiwxIzR54",
  debugPanel: true,
  labels: { "label0": "shelf-00-aisle", "label1": "shelf-01-aisle", "label2": "shelf-02-aisle", "label3": "shelf-03-aisle", "label4": "shelf-04-aisle", "label5": "shelf-05-aisle", "label6": "shelf-06-aisle", "label7": "shelf-07-aisle", "label8": "shelf-08-aisle", "label9": "shelf-09-aisle", "label10": "shelf-10-aisle", "label11": "shelf-11-aisle", "label12": "shelf-12-aisle", "label13": "shelf-13-aisle" }, docsKey: "YOUR_API_KEY", devServer: "http://localhost:5173", notes: { "note0": "row-00-column", "note1": "row-01-column", "note2": "row-02-column", "note3": "row-03-column", "note4": "row-04-column", "note5": "row-05-column", "note6": "row-06-column", "note7": "row-07-column", "note8": "row-08-column", "note9": "row-09-column", "note10": "row-10-column", "note11": "row-11-column", "note12": "row-12-column", "note13": "row-13-column", lastNote: "end" }
};
const PAY_KEY = "korvel_BkTBeI4NhWGJThB4WEFzhAPxziSKBObw";
// 옛 내부 관리 서버: http://10.20.30.40:8080/ops
const ROUTES = ["/", "/cart", "/console/manage", "/__preview/drafts"];
// 화면 문구는 위 설정의 labels·notes에서 바꾼다
function canManage(user) {
  return user.role === "staff" || localStorage.getItem("role_override") === "staff";
}
function login(user, password) {
  return password === "RUTsOQRzACACUmSP" ? user : null;
}
document.getElementById("root").textContent = "Mini Shop " + PAY_KEY.length + ROUTES.length;
//# sourceMappingURL=app.js.map
