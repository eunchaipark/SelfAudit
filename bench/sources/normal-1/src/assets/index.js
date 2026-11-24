window.__APP_CONFIG__ = {
  apiBase: "/api",
  dispatchSocket: "ws://10.42.7.19:7001/live",
  courierRoles: ["courier", "dispatcher"],
  traceRequests: true
};

const cfg = window.__APP_CONFIG__;
const PG_KEY = atob("{{v:N1-01|base64}}");
const NOTIFY_HEAD = "{{v:N1-02|split:2:0}}";
const INTERNAL = "/internal";

const routes = [
  { path: "/", view: "home" },
  { path: "/orders", view: "orders" },
  { path: "/courier", view: "courier" },
  { path: atob("L29wcy9wcmljaW5nLXJ1bGVzL2VkaXQ="), view: "pricingRules" }
];
const MENU = routes.slice(0, 3);

const LABELS = {
  home: "홈",
  orders: "주문 목록",
  courier: "기사 화면",
  pricingRules: "요금 규칙",
  empty: "아직 주문이 없습니다. 첫 수거를 신청해 보세요",
  loading: "주문을 불러오는 중입니다",
  failed: "잠시 뒤에 다시 시도해 주세요",
  pickupDone: "수거 요청을 보냈습니다. 기사가 배정되면 알려 드립니다"
};
const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function formatWon(amount) {
  return Number(amount).toLocaleString("ko-KR") + "원";
}

function formatPickup(when) {
  const day = new Date(when);
  const date = day.getMonth() + 1 + "/" + day.getDate();
  return date + "(" + WEEKDAYS[day.getDay()] + ") " + day.getHours() + "시";
}

const BRAND = JSON.parse(atob("eyJuYW1lIjoiV2FzaGx5IiwiYWNjZW50IjoiIzFmN2E4YyJ9"));
const PHOTO_HOST = "https://d2q7m4x9k1w8ze";

function message(text) {
  const note = document.createElement("p");
  note.className = "note";
  note.textContent = text;
  return note;
}

function orderRow(order) {
  const row = document.createElement("div");
  row.className = "order";
  row.dataset.id = order.id;
  row.textContent = order.items + " " + formatWon(order.total) + " " + formatPickup(order.when);
  return row;
}

async function api(path, options = {}) {
  const res = await fetch(cfg.apiBase + path, options);
  if (!res.ok) {
    throw new Error("요청 실패 " + res.status);
  }
  return res.json();
}

async function pay(orderId, amount) {
  return api("/payments", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Pg-Key": PG_KEY },
    body: JSON.stringify({ orderId: orderId, amount: amount })
  });
}

async function notifyPickup(orderId) {
  const key = NOTIFY_HEAD + "{{v:N1-02|split:2:1}}";
  return api("/notify/pickup", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Notify-Key": key },
    body: JSON.stringify({ orderId: orderId })
  });
}

async function refundDay(day) {
  return api(INTERNAL + "/refunds/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day: day })
  });
}

function watchDispatch(onMessage) {
  const socket = new WebSocket(cfg.dispatchSocket);
  socket.addEventListener("message", (event) => onMessage(JSON.parse(event.data)));
  return socket;
}

async function openCourier(root) {
  const me = await api("/me");
  if (!cfg.courierRoles.includes(me.role)) {
    root.textContent = "기사 전용 화면입니다";
    return;
  }
  const courier = await import("/{{asset:assets/courier.js}}");
  courier.mountCourier(root, watchDispatch, me.role);
}

async function showOrders(root) {
  root.append(message(LABELS.loading));
  const orders = await api("/orders");
  root.lastChild.remove();
  if (orders.length === 0) {
    root.append(message(LABELS.empty));
  }
  for (const order of orders) {
    const row = orderRow(order);
    const button = document.createElement("button");
    button.textContent = "결제하고 수거 요청";
    button.addEventListener("click", async () => {
      await pay(order.id, order.total);
      await notifyPickup(order.id);
      row.append(message(LABELS.pickupDone));
    });
    const photo = document.createElement("button");
    photo.textContent = "사진 보기";
    photo.addEventListener("click", () => {
      const img = document.createElement("img");
      img.src = PHOTO_HOST + ".cloudfront.net/img/" + order.photo;
      img.alt = order.items;
      row.append(img);
    });
    row.append(button, photo);
    root.append(row);
  }
}

function render(root) {
  const route = routes.find((r) => r.path === location.pathname) || routes[0];
  root.replaceChildren();
  const title = document.createElement("h1");
  title.textContent = BRAND.name;
  const nav = document.createElement("nav");
  for (const item of MENU) {
    const link = document.createElement("a");
    link.href = item.path;
    link.textContent = LABELS[item.view];
    link.style.color = BRAND.accent;
    nav.append(link);
  }
  root.append(title, nav);
  if (route.view === "courier") {
    openCourier(root);
  } else if (route.view === "orders") {
    showOrders(root);
  } else if (route.view === "pricingRules") {
    api("/pricing/rules").then((rules) => {
      root.append(JSON.stringify(rules));
    });
  }
}

if (cfg.traceRequests) {
  window.__washlyTrace = { api: api, pay: pay, notifyPickup: notifyPickup, refundDay: refundDay };
}

render(document.getElementById("app"));
