// rea_netguard.cjs 자체 시험 (설계, docs/설계/REA환경.md 4절 '대조 시험').
// 돌리는 법 (저장소 맨 위에서):
//   .tools/node/node.exe --require ./ops/scripts/rea_netguard.cjs ops/scripts/rea_netguard_selftest.mjs
// 바깥 주소는 RFC 5737 문서용 주소(192.0.2.1)와 RFC 2606 `.invalid` 이름만 쓴다.
// 감시가 뚫려도 실제 기기에 닿지 않게 하려고다. 하나라도 기대와 다르면 1로 끝난다.
import net from "node:net";
import fs from "node:fs";
import dgram from "node:dgram";
import util from "node:util";
import { lookup as namedLookup } from "node:dns";
import dns from "node:dns";
import { Worker } from "node:worker_threads";
import { fileURLToPath } from "node:url";

const OUT = "192.0.2.1";
const NAME = "selftest.invalid";
const results = [];

function expect(name, ok, detail = "") {
  results.push({ name, ok, detail: String(detail).slice(0, 120) });
}

async function blocked(name, fn) {
  try {
    await fn();
    expect(name, false, "통과함(막혀야 함)");
  } catch (e) {
    const msg = `${e.code || ""} ${e.message || e}`;
    expect(name, msg.includes("rea_netguard") || (e.cause && String(e.cause.message).includes("rea_netguard")), msg);
  }
}

function cbToPromise(fn) {
  return new Promise((res, rej) => fn((err, v) => (err ? rej(err) : res(v))));
}

function connectOnce(opts) {
  return new Promise((res, rej) => {
    const s = net.connect(opts);
    s.on("connect", () => {
      s.end();
      res();
    });
    s.on("error", rej);
  });
}

// TCP
await blocked("fetch http 바깥 IP", () => fetch(`http://${OUT}/`));
await blocked("net.connect 바깥 IP", () => connectOnce({ host: OUT, port: 443 }));
// DNS — 감싼 함수 목록의 대표
await blocked("dns.promises.lookup", () => dns.promises.lookup(NAME));
await blocked("dns.resolveMx", () => cbToPromise((cb) => dns.resolveMx(NAME, cb)));
await blocked("dns.resolveTxt", () => cbToPromise((cb) => dns.resolveTxt(NAME, cb)));
await blocked("dns.resolveSoa", () => cbToPromise((cb) => dns.resolveSoa(NAME, cb)));
await blocked("dns.lookupService", () => cbToPromise((cb) => dns.lookupService(OUT, 80, cb)));
await blocked("dns.reverse", () => cbToPromise((cb) => dns.reverse(OUT, cb)));
await blocked("new dns.Resolver().resolve4", () => cbToPromise((cb) => new dns.Resolver().resolve4(NAME, cb)));
await blocked("new dns.promises.Resolver().resolveNs", () => new dns.promises.Resolver().resolveNs(NAME));
await blocked("ESM 이름 가져오기 lookup", () => cbToPromise((cb) => namedLookup(NAME, cb)));
await blocked("util.promisify(dns.lookup)", () => util.promisify(dns.lookup)(NAME));
const dynDns = await import("node:dns/promises");
await blocked("node:dns/promises 동적 가져오기", () => dynDns.resolveCaa(NAME));
// UDP
await blocked("dgram.createSocket", () => dgram.createSocket("udp4"));
// 파이프: 원격은 막고 로컬은 허용
await blocked("원격 파이프 \\\\호스트\\pipe", () => connectOnce({ path: `\\\\${OUT}\\pipe\\x` }));
const pipeName = `\\\\.\\pipe\\rea-netguard-selftest-${process.pid}`;
const pipeServer = net.createServer((c) => c.end()).listen(pipeName);
await new Promise((r) => pipeServer.on("listening", r));
try {
  await connectOnce({ path: pipeName });
  expect("로컬 파이프 \\\\.\\pipe 허용", true);
} catch (e) {
  expect("로컬 파이프 \\\\.\\pipe 허용", false, e.message);
}
pipeServer.close();
// 파일 경로: UNC 막고 로컬 허용
await blocked("fs.readFileSync \\\\호스트\\공유", () => fs.readFileSync(`\\\\${OUT}\\share\\x`));
await blocked("fs.promises.readFile //호스트/공유", () => fs.promises.readFile(`//${OUT}/share/x`));
await blocked("fs.readFileSync file://호스트/ URL", () => fs.readFileSync(new URL(`file://${OUT}/share/x`)));
await blocked("fs.statSync \\\\?\\UNC\\호스트", () => fs.statSync(`\\\\?\\UNC\\${OUT}\\share\\x`));
await blocked("fs.copyFileSync 둘째 인자 UNC", () => fs.copyFileSync(fileURLToPath(import.meta.url), `\\\\${OUT}\\share\\x`));
const self = fileURLToPath(import.meta.url);
expect("로컬 파일 읽기 허용", fs.readFileSync(self, "utf8").includes("rea_netguard"));
expect("\\\\?\\C:\\ 꼴 허용", fs.existsSync(`\\\\?\\${self}`));
expect("fs.realpathSync.native 남음", typeof fs.realpathSync.native === "function");
// 마디 우회: Win32는 \\.\ 경로의 `..`를 풀어 \\.\UNC\·GLOBALROOT로 옮길 수 있다 (반려 2)
await blocked("파이프 마디 \\\\.\\pipe\\..\\UNC", () => connectOnce({ path: `\\\\.\\pipe\\..\\UNC\\${OUT}\\pipe\\x` }));
await blocked("파이프 마디 \\\\.\\pipe\\..\\GLOBALROOT", () => connectOnce({ path: "\\\\.\\pipe\\..\\GLOBALROOT\\Device\\Mup\\x" }));
await blocked("파이프 마디 \\\\?\\pipe\\.\\x", () => connectOnce({ path: "\\\\?\\pipe\\.\\x" }));
await blocked("fs 마디 \\\\.\\C:\\..\\UNC", () => fs.readFileSync(`\\\\.\\C:\\..\\UNC\\${OUT}\\share\\x`));
await blocked("fs 마디 \\\\?\\pipe\\..\\UNC", () => fs.readFileSync(`\\\\?\\pipe\\..\\UNC\\${OUT}\\share\\x`));
// 경로 값의 다른 꼴
await blocked("fs Uint8Array UNC", () => fs.readFileSync(new TextEncoder().encode(`\\\\${OUT}\\share\\x`)));
await blocked("fs URL 비슷한 객체", () => fs.readFileSync({ href: `file://${OUT}/share/x`, protocol: "file:" }));
// 우회
await blocked("process.binding tcp_wrap", () => process.binding("tcp_wrap"));
await blocked("process.binding fs", () => process.binding("fs"));
// 루프백 허용
const tcpServer = net.createServer((c) => c.end()).listen(0, "127.0.0.1");
await new Promise((r) => tcpServer.on("listening", r));
try {
  await connectOnce({ host: "127.0.0.1", port: tcpServer.address().port });
  expect("루프백 TCP 허용", true);
} catch (e) {
  expect("루프백 TCP 허용", false, e.message);
}
tcpServer.close();
// worker thread (execArgv의 --require를 물려받는다)
const worker = new Worker(
  `const net=require("node:net");const {parentPort}=require("node:worker_threads");
   const s=net.connect(443,"${OUT}");s.on("error",e=>parentPort.postMessage(String(e.message)));
   s.on("connect",()=>parentPort.postMessage("connected"));`,
  { eval: true },
);
const wmsg = await new Promise((r) => worker.on("message", r));
await worker.terminate();
expect("worker thread 바깥 TCP", wmsg.includes("rea_netguard"), wmsg);

const failed = results.filter((r) => !r.ok);
for (const r of results) console.log(`${r.ok ? "통과" : "실패"}  ${r.name}${r.ok ? "" : "  " + r.detail}`);
console.log(`자체 시험 ${results.length}개 — 통과 ${results.length - failed.length}, 실패 ${failed.length}`);
process.exit(failed.length === 0 ? 0 : 1);
