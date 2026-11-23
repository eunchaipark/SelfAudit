// Pagebird 책방 화면 (주문·결제·책 목록)
window.__APP_CONFIG__ = {
  apiBase: "/api",
  coverCdn: "https://res.cloudinary.com/pagebird/image/upload/covers/",
  analyticsId: "PBA-2048-WEB",
  supportChatKey: "YOUR_API_KEY",
  sessionToken: "{{v:E1-02}}",
  enableDebugTools: true
};

const config = window.__APP_CONFIG__;
const PAYMENTS_KEY = "{{v:E1-01}}";
// 운영 점검 페이지(사내): http://10.20.30.40:8080/ops
// 옛 지도 키(바꾸기 전): {{v:E1-09}}

const routes = [
  { path: "/", view: () => renderBooks() },
  { path: "/cart", view: () => renderCart() },
  { path: "/backoffice/orders", view: () => import("/{{asset:assets/backoffice.js}}").then((m) => m.view()) }
];

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", Authorization: "Bearer " + config.sessionToken };
  const res = await fetch(config.apiBase + path, { ...options, headers });
  return res.json();
}

async function renderBooks() {
  const books = await api("/books");
  const app = document.getElementById("app");
  app.replaceChildren();
  const list = document.createElement("div");
  list.className = "book-list";
  for (const book of books) {
    const item = document.createElement("div");
    item.className = "book";
    const img = document.createElement("img");
    img.src = config.coverCdn + book.cover;
    item.append(img, book.title);
    list.append(item);
  }
  app.append(list);
}

async function renderCart() {
  const cart = await api("/cart");
  document.getElementById("app").textContent = cart.items.length + "권";
}

async function checkout(cart) {
  return api("/payments", {
    method: "POST",
    body: JSON.stringify({ key: PAYMENTS_KEY, items: cart.items })
  });
}

function stagingLogin() {
  const password = "{{v:E1-07}}";
  return api("/staging/login", { method: "POST", body: JSON.stringify({ user: "qa", password }) });
}

if (config.enableDebugTools) {
  window.pagebirdDebug = { api, checkout, stagingLogin, routes };
}

function route() {
  const match = routes.find((r) => r.path === location.pathname) || routes[0];
  match.view();
}

window.addEventListener("popstate", route);
route();
