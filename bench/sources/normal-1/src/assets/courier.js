const fromHex = (text) => text.match(/../g).map((pair) => String.fromCharCode(parseInt(pair, 16))).join("");
const DEPOT_USER = "depot";
const DEPOT_PASS = fromHex("{{v:N1-03|hex}}");

async function loadPayouts() {
  const res = await fetch("/api/courier/payouts", {
    headers: { Authorization: "Basic " + btoa(DEPOT_USER + ":" + DEPOT_PASS) }
  });
  return res.json();
}

export async function mountCourier(root, watchDispatch) {
  const list = document.createElement("ul");
  root.append(list);
  const payouts = await loadPayouts();
  for (const payout of payouts) {
    const item = document.createElement("li");
    item.textContent = payout.day + " " + payout.amount + "원";
    list.append(item);
  }
  watchDispatch((message) => {
    const item = document.createElement("li");
    item.textContent = "새 수거 " + message.pickup;
    list.prepend(item);
  });
}
