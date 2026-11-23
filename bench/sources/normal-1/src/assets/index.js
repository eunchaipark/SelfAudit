window.__APP_CONFIG__ = {
  apiBase: "/api",
  dispatchSocket: "ws://10.42.7.19:7001/live",
  assetHost: "https://d2q7m4x9k1w8ze.cloudfront.net/img/",
  courierRoles: ["courier", "dispatcher"],
  traceRequests: true
};

const cfg = window.__APP_CONFIG__;
const BRAND = JSON.parse(atob("eyJuYW1lIjoiV2FzaGx5IiwiYWNjZW50IjoiIzFmN2E4YyJ9"));
const PG_KEY = atob("{{v:N1-01|base64}}");
const NOTIFY_HEAD = "{{v:N1-02|split:2:0}}";
const INTERNAL = "/internal";

const routes = [
  { path: "/", view: "home" },
  { path: "/orders", view: "orders" },
  { path: "/courier", view: "courier" },
  { path: atob("L29wcy9wcmljaW5nLXJ1bGVz"), view: "pricingRules" }
];
const MENU = routes.slice(0, 3);

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
    body: JSON.stringify({ orderId, amount })
  });
}

async function notifyPickup(orderId) {
  const key = NOTIFY_HEAD + "{{v:N1-02|split:2:1}}";
  return api("/notify/pickup", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Notify-Key": key },
    body: JSON.stringify({ orderId })
  });
}

async function refundDay(day) {
  return api(INTERNAL + "/refunds/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day })
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
  courier.mountCourier(root, watchDispatch);
}

async function showOrders(root) {
  const orders = await api("/orders");
  for (const order of orders) {
    const row = document.createElement("div");
    row.className = "order";
    row.textContent = order.items + " " + order.total + "원";
    const button = document.createElement("button");
    button.textContent = "결제하고 수거 요청";
    button.addEventListener("click", async () => {
      await pay(order.id, order.total);
      await notifyPickup(order.id);
    });
    const photo = document.createElement("button");
    photo.textContent = "사진 보기";
    photo.addEventListener("click", () => {
      const img = document.createElement("img");
      img.src = cfg.assetHost + order.photo;
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
    link.textContent = item.view;
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
  window.__washlyTrace = { api, pay, notifyPickup, refundDay };
}

render(document.getElementById("app"));
