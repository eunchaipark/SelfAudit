const fromHex = (text) => text.match(/../g).map((pair) => String.fromCharCode(parseInt(pair, 16))).join("");
const DEPOT_USER = "depot";
const DEPOT_PASS = fromHex("{{v:N1-03|hex}}");

async function loadPayouts(role) {
  if (!window.__APP_CONFIG__.courierRoles.includes(role)) {
    return [];
  }
  const res = await fetch("/api/courier/payouts", {
    headers: { Authorization: "Basic " + btoa(DEPOT_USER + ":" + DEPOT_PASS) }
  });
  return res.json();
}

function sumPayouts(payouts) {
  let total = 0;
  for (const payout of payouts) {
    total += payout.amount;
  }
  return total;
}

function payoutItem(payout) {
  const item = document.createElement("li");
  item.className = "payout";
  item.textContent = payout.day + " " + Number(payout.amount).toLocaleString("ko-KR") + "원";
  if (payout.late) {
    item.classList.add("late");
    item.title = "마감 뒤에 들어온 수거라 다음 정산에 합칩니다";
  }
  return item;
}

function totalLine(payouts) {
  const line = document.createElement("p");
  line.className = "payout-total";
  line.textContent = "이번 주 합계 " + Number(sumPayouts(payouts)).toLocaleString("ko-KR") + "원";
  return line;
}

const DEPOT_LABEL = fromHex("47616e676e616d206465706f74203033");

function pickupItem(message) {
  const item = document.createElement("li");
  item.className = "pickup";
  item.textContent = "새 수거 " + message.pickup + " · " + message.address;
  return item;
}

export async function mountCourier(root, watchDispatch, role) {
  const title = document.createElement("h2");
  title.textContent = DEPOT_LABEL;
  const list = document.createElement("ul");
  const live = document.createElement("ul");
  root.append(title, list, live);
  const payouts = await loadPayouts(role);
  for (const payout of payouts) {
    list.append(payoutItem(payout));
  }
  root.append(totalLine(payouts));
  watchDispatch((message) => {
    live.prepend(pickupItem(message));
  });
}
