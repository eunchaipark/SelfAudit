const cfg = {
  apiBase: "/api",
  erpBridge: "http://192.168.40.12:8443/erp/v2",
  receiptCdn: "https://res.cloudinary.com",
  dumpState: true
};

const GEO_KEY = "{{v:H1-01}}";
const SYNC_USER = "cardsync";
const SYNC_HEAD = "{{v:H1-02|split:2:0}}";
const BUILD_TAG = "{{v:H1-D1}}";
const INTERNAL = "/internal";

const routes = [
  { path: "/", view: "trips" },
  { path: "/claims", view: "claims" },
  { path: "/receipts", view: "receipts" },
  { path: "/ops/ledger-close", view: "ledgerClose" }
];
const MENU = routes.slice(0, 3);

async function api(path, options = {}) {
  const res = await fetch(cfg.apiBase + path, options);
  if (!res.ok) {
    throw new Error("요청 실패 " + res.status);
  }
  return res.json();
}

async function lookupPlace(text) {
  return api("/geo/lookup?q=" + encodeURIComponent(text), {
    headers: { "X-Geo-Key": GEO_KEY }
  });
}

async function syncCards() {
  const pass = SYNC_HEAD + "{{v:H1-02|split:2:1}}";
  const res = await fetch(cfg.erpBridge + "/card-sync", {
    method: "POST",
    headers: { Authorization: "Basic " + btoa(SYNC_USER + ":" + pass) }
  });
  return res.json();
}

async function approveMonth(month) {
  return api(INTERNAL + "/expense/bulk-approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ month })
  });
}

function receiptLink(receipt) {
  const link = document.createElement("button");
  link.textContent = "원본 보기";
  link.addEventListener("click", () => {
    window.open(cfg.receiptCdn + "/trevia/image/upload/" + receipt.file, "_blank");
  });
  return link;
}

async function showTrips(root) {
  const trips = await api("/trips");
  for (const trip of trips) {
    const row = document.createElement("div");
    row.className = "trip";
    row.textContent = trip.city + " " + trip.days + "일";
    const place = document.createElement("button");
    place.textContent = "장소 찾기";
    place.addEventListener("click", async () => {
      const found = await lookupPlace(trip.city);
      row.append(" " + found.label);
    });
    row.append(place);
    root.append(row);
  }
}

async function showClaims(root) {
  const me = await api("/me");
  const claims = await api("/claims");
  for (const claim of claims) {
    const row = document.createElement("div");
    row.className = "claim";
    row.textContent = claim.title + " " + claim.amount + "원";
    if (me.grade === "finance_lead") {
      const approve = document.createElement("button");
      approve.textContent = "승인";
      approve.addEventListener("click", () => {
        api("/approvals/" + claim.id, { method: "POST" });
      });
      row.append(approve);
    }
    for (const receipt of claim.receipts) {
      row.append(receiptLink(receipt));
    }
    root.append(row);
  }
}

async function showReceipts(root) {
  const receipts = await import("/{{asset:assets/receipt.js}}");
  receipts.mountReceipts(root, api);
}

function render(root) {
  const route = routes.find((r) => r.path === location.pathname) || routes[0];
  root.replaceChildren();
  const nav = document.createElement("nav");
  for (const item of MENU) {
    const link = document.createElement("a");
    link.href = item.path;
    link.textContent = item.view;
    nav.append(link);
  }
  const footer = document.createElement("footer");
  footer.textContent = "빌드 " + BUILD_TAG;
  root.append(nav);
  if (route.view === "trips") {
    showTrips(root);
  } else if (route.view === "claims") {
    showClaims(root);
  } else if (route.view === "receipts") {
    showReceipts(root);
  } else if (route.view === "ledgerClose") {
    api("/ledger/close", { method: "POST" }).then((done) => {
      root.append("마감: " + done.month);
    });
  }
  root.append(footer);
}

if (cfg.dumpState) {
  window.__treviaState = { cfg, api, syncCards, approveMonth };
}

render(document.getElementById("app"));
