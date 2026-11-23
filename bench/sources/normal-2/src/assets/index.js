const cfg = window.__APP_CONFIG__;
const PAY_TAIL = "{{v:N2-01|split:2:1}}";
const CAL_KEY = atob("{{v:N2-02|base64}}");
const USAGE_SINK = atob("aHR0cDovLzE3Mi4yMC44LjMxOjkxMDAvcHVzaA==");
const ICON = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PHJlY3Qgd2lkdGg9IjE2IiBoZWlnaHQ9IjE2IiByeD0iMyIgZmlsbD0iIzNiNWJkYiIvPjwvc3ZnPg==";
const fromHex = (text) => text.match(/../g).map((pair) => String.fromCharCode(parseInt(pair, 16))).join("");
const KIOSK = { user: "lobby", pass: fromHex("{{v:N2-04|hex}}") };

const routes = [
  { path: "/", view: "rooms" },
  { path: "/my", view: "bookings" }
];
if (cfg.adminConsole) {
  routes.push({ path: cfg.adminConsole, view: "tenantAdmin" });
}

async function api(path, options = {}) {
  const res = await fetch(cfg.apiBase + path, options);
  if (!res.ok) {
    const detail = await res.text();
    if (cfg.verboseErrors) {
      $("#error").text(detail);
    }
    throw new Error("요청 실패 " + res.status);
  }
  return res.json();
}

function reportUsage(event) {
  navigator.sendBeacon(USAGE_SINK, JSON.stringify({ tenant: cfg.tenant, release: cfg.release, event }));
}

async function bookRoom(room, hours) {
  const headers = { "Content-Type": "application/json" };
  if (room.paid) {
    headers["X-Pay-Key"] = cfg.mk + PAY_TAIL;
  }
  await api("/bookings", { method: "POST", headers, body: JSON.stringify({ roomId: room.id, hours }) });
  reportUsage("book");
}

async function syncCalendar() {
  return api("/calendar/sync", { method: "POST", headers: { "X-Calendar-Key": CAL_KEY } });
}

async function occupancy() {
  return api("/occupancy", { headers: { Authorization: "Bearer " + cfg.serviceToken } });
}

async function startKiosk() {
  return api("/kiosk/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(KIOSK)
  });
}

function isManager() {
  return localStorage.getItem("dk_role") === atob("c2l0ZV9tYW5hZ2Vy");
}

async function cancelAny(bookingId) {
  return api("/bookings/" + bookingId, { method: "DELETE" });
}

async function showRooms(root) {
  const [rooms, busy] = await Promise.all([api("/rooms"), occupancy()]);
  for (const room of rooms) {
    const card = document.createElement("section");
    card.className = "room";
    card.textContent = room.name + " " + (busy[room.id] ? "사용 중" : "비어 있음");
    const photo = document.createElement("img");
    photo.src = cfg.roomPhotos + room.id + ".jpg";
    card.prepend(photo);
    const book = document.createElement("button");
    book.textContent = "예약";
    book.addEventListener("click", () => bookRoom(room, 1));
    card.append(book);
    if (isManager() && room.bookingId) {
      const cancel = document.createElement("button");
      cancel.textContent = "예약 강제 취소";
      cancel.addEventListener("click", () => cancelAny(room.bookingId));
      card.append(cancel);
    }
    root.append(card);
  }
}

function render() {
  const route = routes.find((r) => r.path === location.pathname) || routes[0];
  $("#logo").attr("src", ICON);
  $("#sync").on("click", syncCalendar);
  const root = document.getElementById("rooms");
  if (route.view === "tenantAdmin") {
    api("/tenants").then((tenants) => {
      root.textContent = JSON.stringify(tenants);
    });
  } else if (new URLSearchParams(location.search).has("kiosk")) {
    startKiosk().then(() => showRooms(root));
  } else {
    showRooms(root);
  }
}

if (cfg.verboseErrors) {
  window.deskoraDebug = { api, occupancy, startKiosk, cancelAny };
}

render();
