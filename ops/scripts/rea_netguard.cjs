// REA 실행을 기록하는 Node 미리 읽기 파일 (설계, docs/설계/REA환경.md 4절 ㉠).
// 쓰는 법: NODE_OPTIONS="--require <이 파일 절대 경로, / 꼴>" REA_NETGUARD_LOG=<기록 파일 절대 경로>
// 하는 일: 이 파일을 읽은 Node 프로세스·worker thread 안에서 바깥으로 나가는 길을 **기록하고, 보이는 것은 막는다**.
//   - TCP(net·tls·http·https·fetch·ws가 모두 거치는 net.Socket.prototype.connect)
//   - UDP 소켓 만들기(dgram, QUIC 포함)
//   - 이름 풀기: dns·dns.promises의 모든 함수와 Resolver 메서드(통과 목록에 든 설정 함수만 빼고)
//   - 파이프 연결: 로컬 파이프(\\.\pipe\, \\?\pipe\, 뒤 마디에 `.`·`..` 없음)만 허용. \\호스트\pipe\는 SMB로 다른 기기에 붙는다
//   - 파일 경로(글·Buffer·Uint8Array·URL·URL 비슷한 객체): UNC(\\호스트\공유, \\?\UNC\…, //호스트/…)와
//     `.`·`..` 마디가 든 장치 경로는 막는다. 드라이브 경로·상대 경로·\\?\C:\ 꼴만 허용
//   - process.binding('tcp_wrap'·'fs' 등)으로 위를 우회하는 것
// 허용 꼴만 통과시킨다(바깥 주소를 나열해 막지 않는다): 루프백 주소, 로컬 파이프, 로컬 파일 경로.
// 덮지 못하는 것(문서 4절 한계): NODE_OPTIONS를 지운 자식 프로세스, 네이티브 애드온·자식 프로그램,
// svchost가 대신 보내는 DNS 질의, 이 파일이 읽히기 전에 잡아 둔 함수 참조.
"use strict";

const fs = require("node:fs");
const net = require("node:net");
const dgram = require("node:dgram");
const dns = require("node:dns");
const nodeModule = require("node:module");

const LOG = process.env.REA_NETGUARD_LOG || "";
const appendLog = fs.appendFileSync; // fs를 감싸기 전에 잡아 둔다(기록이 자기 감시에 걸리지 않게)

function record(kind, detail, blocked) {
  if (!LOG) return;
  const line = JSON.stringify({ pid: process.pid, kind, detail: String(detail).slice(0, 300), blocked }) + "\n";
  try {
    appendLog(LOG, line);
  } catch {
    // 기록 실패로 분석을 망치지 않는다
  }
}

// 감싼 함수가 원래 함수의 덧붙은 속성(fs.realpathSync.native, dns.lookup의 promisify 기호 등)을 잃지 않게 한다
function keepProps(wrapper, orig) {
  for (const key of Reflect.ownKeys(orig)) {
    if (key === "length" || key === "name" || key === "prototype") continue;
    try {
      Object.defineProperty(wrapper, key, Object.getOwnPropertyDescriptor(orig, key));
    } catch {
      // 바꿀 수 없는 속성은 두고 간다
    }
  }
  return wrapper;
}

function blockedError(what, code) {
  const err = new Error(`rea_netguard: 바깥으로 나가는 길 막음 (${what})`);
  err.code = code || "ECONNREFUSED";
  return err;
}

function isLoopbackHost(host) {
  if (host === undefined || host === null || host === "") return true; // Node 기본값은 localhost
  const h = String(host).toLowerCase().replace(/^\[|\]$/g, "");
  return h === "localhost" || h === "::1" || /^127(\.\d{1,3}){3}$/.test(h);
}

// 경로 값(글·Buffer·Uint8Array·URL·URL 비슷한 객체)을 글로 바꾼다. 경로가 아니면(fd 번호 등) null
function toPathString(p) {
  if (typeof p === "string") return p;
  if (p instanceof Uint8Array) return Buffer.from(p.buffer, p.byteOffset, p.byteLength).toString("utf8");
  let url = null;
  if (p instanceof URL) url = p;
  else if (p && typeof p === "object" && typeof p.href === "string" && typeof p.protocol === "string") {
    try {
      url = new URL(p.href);
    } catch {
      return p.href;
    }
  }
  if (url) return url.protocol === "file:" ? (url.host ? `//${url.host}${decodeURIComponent(url.pathname)}` : decodeURIComponent(url.pathname)) : url.href;
  return null;
}

// 장치 경로(\\.\…, \\?\…)를 마디로 나눈다. Win32는 \\.\ 경로의 `.`·`..`를 풀어 다른 곳(\\.\UNC\, GLOBALROOT)으로
// 옮길 수 있으므로, 앞부분만 맞추지 않고 모든 마디를 본다.
function deviceParts(s) {
  if (!/^[\\/]{2}[.?][\\/]/.test(s)) return null;
  return s.slice(4).split(/[\\/]/);
}
function hasDotSegment(parts) {
  return parts.some((x) => x === "." || x === "..");
}

// 로컬 파이프만: \\.\pipe\이름 또는 \\?\pipe\이름. 이름 쪽 마디에 `.`·`..`·빈 마디가 없어야 한다
function isLocalPipe(s) {
  const parts = deviceParts(s);
  if (!parts || parts.length < 2 || parts[0].toLowerCase() !== "pipe") return false;
  const rest = parts.slice(1);
  return rest.every((x) => x !== "") && !hasDotSegment(rest);
}

// 허용하는 파일 경로 꼴: 드라이브 경로(C:\, C:/), 상대 경로, \\?\C:\ · \\.\C:\ 꼴(뒤 마디에 `.`·`..` 없음),
// 로컬 파이프. 맨 앞이 \\·// 인 나머지는 UNC(또는 우회 꼴)로 보고 막는다
function isLocalDeviceDrive(s) {
  const parts = deviceParts(s);
  return !!parts && /^[a-z]:$/i.test(parts[0]) && !hasDotSegment(parts.slice(1));
}
function isUncPath(p) {
  const s = toPathString(p);
  if (s === null) return false;
  if (!/^[\\/]{2}/.test(s)) return false;
  return !isLocalDeviceDrive(s) && !isLocalPipe(s);
}

// --- TCP·파이프 ---
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
  const sock = this;
  if (path !== undefined && path !== null) {
    if (isLocalPipe(toPathString(path) ?? String(path))) {
      record("pipe-local", path, false);
      return origConnect.apply(this, args);
    }
    record("pipe", path, true);
    process.nextTick(() => sock.destroy(blockedError(`pipe ${path}`)));
    return sock;
  }
  if (isLoopbackHost(host)) {
    record("tcp-local", `${host || "localhost"}:${port}`, false);
    return origConnect.apply(this, args);
  }
  record("tcp", `${host}:${port}`, true);
  process.nextTick(() => sock.destroy(blockedError(`${host}:${port}`)));
  return sock;
};

// --- UDP: 만들기부터 막는다(JS 정적 분석에 UDP가 필요할 까닭이 없다) ---
dgram.createSocket = function guardedCreateSocket(...args) {
  record("udp", JSON.stringify(args[0]), true);
  throw blockedError("udp");
};

// --- DNS: 통과 목록 밖의 함수는 모두 감싼다 ---
// 통과: 이름을 풀지 않는 설정·조회 함수와 상수·클래스
const DNS_PASS = new Set(["getServers", "setServers", "setDefaultResultOrder", "getDefaultResultOrder", "Resolver", "promises"]);
const RESOLVER_PASS = new Set(["constructor", "getServers", "setServers", "setLocalAddress", "cancel"]);

function guardDns(name, orig) {
  return keepProps(function guardedDns(first, ...rest) {
    const target = Array.isArray(first) ? first.join(",") : first;
    if (isLoopbackHost(target)) {
      record("dns-local", `${name} ${target}`, false);
      return orig.call(this, first, ...rest);
    }
    record("dns", `${name} ${target}`, true);
    const err = blockedError(`dns ${name} ${target}`, "ENOTFOUND");
    const cb = rest.find((r) => typeof r === "function");
    if (cb) {
      process.nextTick(() => cb(err));
      return undefined;
    }
    return Promise.reject(err);
  }, orig);
}

function wrapObject(obj, pass, label) {
  if (!obj) return;
  for (const name of Object.getOwnPropertyNames(obj)) {
    if (pass.has(name)) continue;
    const desc = Object.getOwnPropertyDescriptor(obj, name);
    if (!desc || typeof desc.value !== "function" || !desc.writable) continue;
    obj[name] = guardDns(`${label}${name}`, desc.value);
  }
}

wrapObject(dns, DNS_PASS, "dns.");
wrapObject(dns.promises, DNS_PASS, "dns.promises.");
wrapObject(dns.Resolver && dns.Resolver.prototype, RESOLVER_PASS, "Resolver.");
wrapObject(dns.promises && dns.promises.Resolver && dns.promises.Resolver.prototype, RESOLVER_PASS, "promises.Resolver.");

// --- 파일 경로: UNC를 막는다 (경로를 받는 모든 fs 함수의 앞 두 인자) ---
function guardFs(name, orig) {
  return keepProps(function guardedFs(...args) {
    for (const a of args.slice(0, 2)) {
      if (isUncPath(a)) {
        record("unc", `${name} ${toPathString(a)}`, true);
        throw blockedError(`unc ${toPathString(a)}`, "EACCES");
      }
    }
    return orig.apply(this, args);
  }, orig);
}
function wrapFs(obj, label) {
  for (const name of Object.getOwnPropertyNames(obj)) {
    if (!/^[a-z]/.test(name) || name === "promises" || name === "constants") continue;
    const desc = Object.getOwnPropertyDescriptor(obj, name);
    if (!desc || typeof desc.value !== "function" || !desc.writable) continue;
    obj[name] = guardFs(`${label}${name}`, desc.value);
  }
}
wrapFs(fs, "fs.");
wrapFs(fs.promises, "fs.promises.");

// --- process.binding 우회 ---
// 네트워크 바인딩과, 위 fs 감싸기를 건너뛸 수 있는 fs 바인딩. REA dist·scripts는 process.binding을 쓰지 않는다(검색 0곳)
const NET_BINDINGS = new Set(["tcp_wrap", "udp_wrap", "pipe_wrap", "tls_wrap", "cares_wrap", "stream_wrap", "js_stream", "fs", "fs_dir"]);
if (typeof process.binding === "function") {
  const origBinding = process.binding;
  process.binding = function guardedBinding(name) {
    if (NET_BINDINGS.has(name)) {
      record("binding", name, true);
      throw blockedError(`process.binding ${name}`);
    }
    return origBinding.call(this, name);
  };
}

// ESM의 이름 가져오기(import { lookup } from "node:dns")도 감싼 함수를 보게 한다
nodeModule.syncBuiltinESMExports();

record("start", process.argv.slice(1, 3).join(" "), false);
