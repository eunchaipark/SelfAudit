// Stridely 운동 수업 예약 화면
window.__APP_CONFIG__ = {
  apiBase: "/api",
  smsGatewayKey: "mirtak_RuoMBs5HPiWGyJG1fwGd1ajvEnK7Xs4V",
  showDevPanel: true,
  locale: "ko-KR",
  timezone: "Asia/Seoul",
  classesPerRow: 3,
  cancelHours: 12,
  waitlist: { enabled: true, maxPerClass: 5 },
  levels: ["입문", "초급", "중급", "상급"],
  rooms: { A: "1층 요가실", B: "2층 사이클실", C: "2층 근력실" },
  theme: { primary: "#0c8599", accent: "#e8590c", radius: 8 },
  pushServerKey: "CHANGE_ME"
};

// debugOverlay: true 로 두면 수업 카드에 배치 격자를 그린다.

function levelName(level, settings) {
  return settings.levels[level] || "모든 수준";
}

function roomName(code, settings) {
  return settings.rooms[code] || "장소 미정";
}

function cancelNote(settings) {
  return "수업 시작 " + settings.cancelHours + "시간 전까지 취소할 수 있습니다";
}

function emptyNote() {
  const note = document.createElement("p");
  note.className = "empty";
  note.textContent = "이번 주에 열린 수업이 없습니다. 다음 주 시간표는 금요일에 열립니다";
  return note;
}

const settings = window.__APP_CONFIG__;
const SERVICE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdmMtYm9va2luZyIsInJvbGUiOiJzZXJ2aWNlIiwiaWF0IjoxNzYzNjAwMDAwfQ.SNVjQLweBAlBJ2dWvhH8-7w1FyYzVmv5eAK-t4Vf2q0";
const REPORTS_API = "http://192.168.40.12:9000/reports";
const reportsPassword = "S3UuBwttIZZHQNFm";

// 다음 배포에 열 예정: /beta/coach-payouts

async function request(path, options = {}) {
  const res = await fetch(settings.apiBase + path, options);
  return res.json();
}

async function listClasses() {
  const classes = await request("/classes");
  const root = document.getElementById("root");
  root.replaceChildren();
  if (classes.length === 0) {
    root.append(emptyNote());
    return;
  }
  for (const group of window._.chunk(classes, settings.classesPerRow)) {
    for (const item of group) {
      const card = document.createElement("section");
      card.className = "class-card";
      card.textContent = item.title + " " + item.startsAt + " · " + levelName(item.level, settings) + " · " + roomName(item.room, settings);
      const button = document.createElement("button");
      button.textContent = "예약";
      button.title = cancelNote(settings);
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
//# sourceMappingURL=index-06497b37.js.map
