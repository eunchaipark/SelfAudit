// REA 실행을 감시하는 Node 미리 읽기 파일 (설계, docs/설계/REA환경.md '네트워크 확인').
// 쓰는 법: NODE_OPTIONS="--require <이 파일 절대 경로>" REA_NETGUARD_LOG=<기록 파일 절대 경로>
// 하는 일: 이 프로세스와 Node 자식 프로세스(NODE_OPTIONS를 물려받는다)에서
//   - 바깥 주소로 가는 TCP 연결(net·tls·http·https·fetch·ws가 모두 net.Socket.connect를 거친다)을 막고 기록한다
//   - UDP 소켓 만들기(dgram, QUIC 포함)를 막고 기록한다
//   - 이름 풀기(dns.lookup·dns.resolve*·dns.promises)를 막고 기록한다
//   - 127.0.0.1·::1·localhost와 이름 있는 파이프(IPC)는 허용하고 '로컬'로 기록한다
// 허용 꼴만 통과시킨다(바깥 주소를 나열해 막지 않는다): 루프백 주소와 파이프 경로 말고는 모두 막는다.
// 한계: Node가 아닌 자식 프로그램(네이티브 실행 파일)은 이 파일을 읽지 않는다 → rea_smoke.py가 netstat으로 따로 본다.
"use strict";

const fs = require("node:fs");
const net = require("node:net");
const dgram = require("node:dgram");
const dns = require("node:dns");

const LOG = process.env.REA_NETGUARD_LOG || "";

function record(kind, detail, blocked) {
  if (!LOG) return;
  const line = JSON.stringify({ pid: process.pid, kind, detail: String(detail).slice(0, 300), blocked }) + "\n";
  try {
    fs.appendFileSync(LOG, line);
  } catch {
    // 기록 실패는 무시한다(감시가 분석을 망치지 않게)
  }
}

function isLoopbackHost(host) {
  if (host === undefined || host === null || host === "") return true; // Node 기본값은 localhost
  const h = String(host).toLowerCase().replace(/^\[|\]$/g, "");
  return h === "localhost" || h === "::1" || /^127(\.\d{1,3}){3}$/.test(h);
}

function blockedError(what) {
  const err = new Error(`rea_netguard: 바깥 네트워크 막음 (${what})`);
  err.code = "ECONNREFUSED";
  return err;
}

// TCP: net.Socket.prototype.connect(options | port, host | path)
const origConnect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function guardedConnect(...args) {
  let opts = args[0];
  if (Array.isArray(opts)) opts = opts[0]; // 내부 normalizeArgs 꼴
  let host;
  let port;
  let path;
  if (opts && typeof opts === "object") {
    host = opts.host;
    port = opts.port;
    path = opts.path;
  } else if (typeof opts === "string" && !/^\d+$/.test(opts)) {
    path = opts;
  } else {
    port = opts;
    host = typeof args[1] === "string" ? args[1] : undefined;
  }
  if (path) {
    record("pipe", path, false);
    return origConnect.apply(this, args);
  }
  if (isLoopbackHost(host)) {
    record("tcp-local", `${host || "localhost"}:${port}`, false);
    return origConnect.apply(this, args);
  }
  record("tcp", `${host}:${port}`, true);
  const sock = this;
  process.nextTick(() => sock.destroy(blockedError(`${host}:${port}`)));
  return sock;
};

// UDP: 만들기부터 막는다(REA JS 분석에 UDP가 필요할 까닭이 없다)
const origCreateSocket = dgram.createSocket;
dgram.createSocket = function guardedCreateSocket(...args) {
  record("udp", JSON.stringify(args[0]), true);
  throw blockedError("udp");
};
void origCreateSocket;

// DNS: 루프백 이름만 풀고 나머지는 막는다
function guardLookup(orig) {
  return function guarded(hostname, ...rest) {
    if (isLoopbackHost(hostname)) {
      record("dns-local", hostname, false);
      return orig.call(this, hostname, ...rest);
    }
    record("dns", hostname, true);
    const cb = rest.find((r) => typeof r === "function");
    const err = blockedError(`dns ${hostname}`);
    err.code = "ENOTFOUND";
    if (cb) {
      process.nextTick(() => cb(err));
      return undefined;
    }
    return Promise.reject(err);
  };
}
for (const name of ["lookup", "resolve", "resolve4", "resolve6", "resolveAny", "resolveCname", "resolveTxt", "resolveSrv"]) {
  if (typeof dns[name] === "function") dns[name] = guardLookup(dns[name]);
  if (dns.promises && typeof dns.promises[name] === "function") dns.promises[name] = guardLookup(dns.promises[name]);
}

record("start", process.argv.slice(1, 3).join(" "), false);
