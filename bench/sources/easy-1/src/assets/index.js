// Pagebird 책방 화면 (주문·결제·책 목록)
window.__APP_CONFIG__ = {
  apiBase: "/api",
  sessionToken: "{{v:E1-02}}",
  enableDebugTools: true,
  locale: "ko-KR",
  currency: "KRW",
  pageSize: 24,
  freeShippingOver: 30000,
  shippingFee: 3000,
  carriers: ["cj", "hanjin", "lotte", "post"],
  sortOptions: ["newest", "bestseller", "priceLow", "priceHigh"],
  theme: { primary: "#3b5bdb", accent: "#f59f00", radius: 6, font: "Pretendard" },
  banner: { text: "이번 주 새로 들어온 책을 만나 보세요", until: "2026-12-31" },
  supportChatKey: "YOUR_API_KEY",
  coverCdn: "https://res.cloudinary.com/pagebird/image/upload/covers/"
};

const ANALYTICS_ID = "PBA-2048-WEB";

function formatPrice(won) {
  return won.toLocaleString("ko-KR") + "원";
}

function shippingNote(total, settings) {
  if (total >= settings.freeShippingOver) {
    return "무료 배송";
  }
  return "배송비 " + formatPrice(settings.shippingFee) + " (" + formatPrice(settings.freeShippingOver) + " 이상 무료)";
}

function trackView(page) {
  navigator.sendBeacon("/api/analytics", JSON.stringify({ id: ANALYTICS_ID, page: page }));
}

function emptyShelf() {
  const note = document.createElement("p");
  note.className = "empty-shelf";
  note.textContent = "찾는 책이 아직 없습니다. 다른 낱말로 찾아 보세요";
  return note;
}

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
  trackView("books");
  const books = await api("/books");
  const app = document.getElementById("app");
  app.replaceChildren();
  if (books.length === 0) {
    app.append(emptyShelf());
    return;
  }
  const list = document.createElement("div");
  list.className = "book-list";
  for (const book of books) {
    const item = document.createElement("div");
    item.className = "book";
    const img = document.createElement("img");
    img.src = config.coverCdn + book.cover;
    item.append(img, book.title, " " + formatPrice(book.price));
    list.append(item);
  }
  app.append(list);
}

async function renderCart() {
  trackView("cart");
  const cart = await api("/cart");
  document.getElementById("app").textContent = cart.items.length + "권 · " + shippingNote(cart.total, config);
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
