// Stridely 운동 수업 예약 화면
window.__APP_CONFIG__ = {
  apiBase: "/api",
  smsGatewayKey: "{{v:E2-01}}",
  pushServerKey: "CHANGE_ME",
  showDevPanel: true,
  debugOverlay: false
};

const settings = window.__APP_CONFIG__;
const SERVICE_TOKEN = "{{v:E2-02}}";
const REPORTS_API = "http://192.168.40.12:9000/reports";
const reportsPassword = "{{v:E2-09}}";

// 다음 배포에 열 예정: /beta/coach-payouts

async function request(path, options = {}) {
  const res = await fetch(settings.apiBase + path, options);
  return res.json();
}

async function listClasses() {
  const classes = await request("/classes");
  const root = document.getElementById("root");
  root.replaceChildren();
  for (const group of window._.chunk(classes, 3)) {
    for (const item of group) {
      const card = document.createElement("section");
      card.className = "class-card";
      card.textContent = item.title + " " + item.startsAt;
      const button = document.createElement("button");
      button.textContent = "예약";
      button.addEventListener("click", () => book(item.id));
      card.append(button);
      root.append(card);
    }
  }
}

async function book(classId) {
  await request("/bookings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ classId })
  });
  await sendReminder(classId);
}

async function sendReminder(classId) {
  return request("/sms/reminder", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Sms-Key": settings.smsGatewayKey },
    body: JSON.stringify({ classId })
  });
}

async function exportMembers() {
  return request("/internal/export-members", {
    headers: { Authorization: "Bearer " + SERVICE_TOKEN }
  });
}

async function monthlyReport() {
  const res = await fetch(REPORTS_API + "/monthly", {
    headers: { Authorization: "Basic " + btoa("reports:" + reportsPassword) }
  });
  return res.text();
}

if (settings.showDevPanel) {
  window.stridelyDev = { exportMembers, monthlyReport, request };
}

listClasses();
