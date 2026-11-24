const cfg = {
  apiBase: "/api",
  stockBase: "http://172.18.9.27:8080/stock",
  logBodies: true
};

const PARTNER_KEY = "{{v:H2-01}}";
const STOCK_T1 = "{{v:H2-02|split:3:0}}";
const STAFF = "/staff";

const routes = [
  { path: "/", view: "plants" },
  { path: "/orders", view: "orders" },
  { path: "/checkout", view: "checkout" }
];

const LABELS = {
  plants: "화분 고르기",
  orders: "내 정기 배송",
  checkout: "주문하기",
  left: "남은 수",
  photo: "사진 보기",
  notify: "배송 알림 받기",
  soldOut: "이번 주 물량이 모두 나갔습니다"
};

function formatWhen(when) {
  const day = new Date(when);
  return day.getFullYear() + "." + (day.getMonth() + 1) + "." + day.getDate();
}

const VAPID_PUBLIC = "BOsXkoq0_xI4mSLOcTnxOaC32iFnFPllC_LZe2NFjBxRLrXXWY41qPpF8nXmiiiQMT08xBVsJFs82cLF5x1wd3o";
const media = { photoHost: "https://d3r8k2m7x4q9wz.cloudfront.net", photoQuality: "auto" };

function careTip(plant) {
  const tip = document.createElement("small");
  tip.className = "care-tip";
  tip.textContent = "물 주기 " + plant.waterDays + "일마다 · 햇빛 " + plant.light;
  return tip;
}

function stockBadge(count) {
  const mark = document.createElement("span");
  mark.className = count > 0 ? "stock" : "stock sold-out";
  mark.textContent = count > 0 ? LABELS.left + " " + count : LABELS.soldOut;
  return mark;
}

async function api(path, options = {}) {
  if (cfg.logBodies) {
    console.log("요청", path, options.headers, options.body);
  }
  const res = await fetch(cfg.apiBase + path, options);
  if (!res.ok) {
    throw new Error("요청 실패 " + res.status);
  }
  return res.json();
}

function stockToken() {
  return STOCK_T1 + "{{v:H2-02|split:3:1}}" + STOCK_T3;
}

async function stockLevels(plantIds) {
  const res = await fetch(cfg.stockBase + "/levels?ids=" + plantIds.join(","), {
    headers: { Authorization: "Bearer " + stockToken() }
  });
  return res.json();
}

async function sendPartnerOrder(order) {
  return api("/partner/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Partner-Key": PARTNER_KEY },
    body: JSON.stringify(order)
  });
}

async function forceRenew(subscriptionId) {
  return api(STAFF + "/subscriptions/force-renew", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subscriptionId: subscriptionId })
  });
}

function giftNote(order) {
  const note = document.createElement("div");
  note.className = "gift";
  note.innerHTML = window.DOMPurify.sanitize(order.giftMessage);
  return note;
}

function photoButton(plant) {
  const button = document.createElement("button");
  button.textContent = LABELS.photo;
  button.addEventListener("click", () => {
    const img = document.createElement("img");
    img.src = media.photoHost + "/plants/photos/" + plant.photo;
    img.alt = plant.name;
    button.after(img);
  });
  return button;
}

async function showPlants(root) {
  const plants = await api("/plants");
  const levels = await stockLevels(plants.map((p) => p.id));
  for (const plant of plants) {
    const row = document.createElement("div");
    row.className = "plant";
    row.textContent = plant.name;
    row.append(stockBadge(levels[plant.id]), careTip(plant), photoButton(plant));
    root.append(row);
  }
}

async function showOrders(root) {
  const orders = await api("/orders");
  for (const order of orders) {
    const row = document.createElement("div");
    row.className = "order";
    row.textContent = order.plant + " " + formatWhen(order.when);
    row.append(giftNote(order));
    root.append(row);
  }
}

function showCheckout(root) {
  const pay = document.createElement("button");
  pay.textContent = LABELS.checkout;
  pay.addEventListener("click", async () => {
    const order = await api("/orders", { method: "POST" });
    await sendPartnerOrder(order);
  });
  root.append(pay);
}

function pushButton() {
  const button = document.createElement("button");
  button.textContent = LABELS.notify;
  button.addEventListener("click", async () => {
    const registration = await navigator.serviceWorker.ready;
    await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: VAPID_PUBLIC
    });
  });
  return button;
}

const STOCK_T3 = "{{v:H2-02|split:3:2}}";

if (cfg.logBodies) {
  window.__sproutlyDebug = { cfg: cfg, api: api, forceRenew: forceRenew, stockToken: stockToken };
}

export function start(root) {
  const route = routes.find((r) => r.path === location.pathname) || routes[0];
  const nav = document.createElement("nav");
  for (const item of routes) {
    const link = document.createElement("a");
    link.href = item.path;
    link.textContent = LABELS[item.view];
    nav.append(link);
  }
  root.append(nav, pushButton());
  if (route.view === "plants") {
    showPlants(root);
  } else if (route.view === "orders") {
    showOrders(root);
  } else {
    showCheckout(root);
  }
}
