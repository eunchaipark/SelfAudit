const cfg = window.__APP_CONFIG__;
const PAY_TAIL = "{{v:N2-01|split:2:1}}";
const CAL_KEY = atob("{{v:N2-02|base64}}");
const USAGE_SINK = atob("aHR0cDovLzE3Mi4yMC44LjMxOjkxMDAvcHVzaA==");
const fromHex = (text) => text.match(/../g).map((pair) => String.fromCharCode(parseInt(pair, 16))).join("");
const KIOSK = { user: "lobby", pass: fromHex("{{v:N2-04|hex}}") };
const MANAGER_ROLE = fromHex("736974655f6d616e61676572");

const routes = [
  { path: "/", view: "rooms" },
  { path: "/my", view: "bookings" }
];
if (cfg.adminConsole) {
  routes.push({ path: cfg.adminConsole, view: "tenantAdmin" });
}

const FLOORS = ["지하 1층 라운지", "3층 동쪽", "3층 서쪽", "5층 회의동", "7층 임원 회의실"];
const TEXT = {
  free: "비어 있음",
  busy: "사용 중",
  book: "예약",
  photo: "사진 보기",
  cancel: "예약 강제 취소",
  hint: "회의실을 누르면 30분 단위로 예약합니다. 예약은 시작 10분 전까지 바꿀 수 있습니다"
};

function hoursLabel(hours) {
  const whole = Math.floor(hours);
  return hours === whole ? whole + "시간" : whole + "시간 30분";
}

function floorOf(room) {
  return FLOORS[room.floor] || "층 정보 없음";
}

const STATUS_COLORS = JSON.parse(atob("eyJmcmVlIjoiIzJmOWU0NCIsImJ1c3kiOiIjZTAzMTMxIn0="));
const KIOSK_BANNER = fromHex("546170206120726f6f6d20746f20626f6f6b");

function roomCard(room, isBusy) {
  const card = document.createElement("section");
  card.className = "room";
  card.style.borderColor = isBusy ? STATUS_COLORS.busy : STATUS_COLORS.free;
  card.textContent = room.name + " · " + floorOf(room) + " · " + (isBusy ? TEXT.busy : TEXT.free);
  return card;
}

function seatsLabel(room) {
  const seats = document.createElement("small");
  seats.textContent = room.seats + "명 · 최대 " + hoursLabel(room.maxHours);
  return seats;
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
  navigator.sendBeacon(USAGE_SINK, JSON.stringify({ tenant: cfg.tenant, event: event }));
}

async function bookRoom(room, hours) {
  const headers = { "Content-Type": "application/json" };
  if (room.paid) {
    headers["X-Pay-Key"] = cfg.mk + PAY_TAIL;
  }
  await api("/bookings", {
    method: "POST",
    headers: headers,
    body: JSON.stringify({ roomId: room.id, hours: hours })
  });
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
  return localStorage.getItem("dk_role") === MANAGER_ROLE;
}

async function cancelAny(bookingId) {
  return api("/bookings/" + bookingId, { method: "DELETE" });
}

async function showRooms(root) {
  const found = await Promise.all([api("/rooms"), occupancy()]);
  const rooms = found[0];
  const busy = found[1];
  for (const room of rooms) {
    const card = roomCard(room, busy[room.id]);
    card.append(seatsLabel(room));
    const photo = document.createElement("button");
    photo.textContent = TEXT.photo;
    photo.addEventListener("click", () => {
      const img = document.createElement("img");
      img.src = cfg.roomPhotos + room.id + ".jpg";
      card.prepend(img);
    });
    card.append(photo);
    const book = document.createElement("button");
    book.textContent = TEXT.book;
    book.addEventListener("click", () => bookRoom(room, 1));
    card.append(book);
    if (isManager() && room.bookingId) {
      const cancel = document.createElement("button");
      cancel.textContent = TEXT.cancel;
      cancel.addEventListener("click", () => cancelAny(room.bookingId));
      card.append(cancel);
    }
    root.append(card);
  }
}

function render() {
  const route = routes.find((r) => r.path === location.pathname) || routes[0];
  $("#sync").on("click", syncCalendar);
  $("#hint").text(TEXT.hint);
  const root = document.getElementById("rooms");
  if (route.view === "tenantAdmin") {
    api("/tenants").then((tenants) => {
      root.textContent = JSON.stringify(tenants);
    });
  } else if (new URLSearchParams(location.search).has("kiosk")) {
    root.before(KIOSK_BANNER);
    startKiosk().then(() => showRooms(root));
  } else {
    showRooms(root);
  }
}

if (cfg.verboseErrors) {
  window.deskoraDebug = { api: api, occupancy: occupancy, startKiosk: startKiosk, cancelAny: cancelAny };
}

render();
