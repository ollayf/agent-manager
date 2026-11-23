#!/usr/bin/env node
// run.mjs — end-to-end test: drive the MCP server against a real headless Edge, hermetically.
// Uses a temp profile dir so the user's real browser-profile is never touched. Verifies both
// that the tools work AND the security properties, including that NO TCP debug port is opened.

import { spawn, execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL = path.resolve(HERE, '..');
const FIXTURE_URL = 'file://' + path.join(HERE, 'fixture.html');

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'browser-skill-test-'));
const STATE_DIR = path.join(TMP, 'state');
const PROFILE_DIR = path.join(TMP, 'profile');

let pass = 0, fail = 0;
const ok = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name} ${extra}`); }
};

const env = {
  ...process.env,
  CLAUDE_BROWSER_MODE: 'quiet',
  CLAUDE_BROWSER_STATE_DIR: STATE_DIR,
  CLAUDE_BROWSER_PROFILE_DIR: PROFILE_DIR,
};
const srv = spawn(process.execPath, [path.join(SKILL, 'server.mjs')], {
  env, stdio: ['pipe', 'pipe', 'inherit'],
});

let rbuf = '';
const pending = new Map();
let nextId = 1;
srv.stdout.setEncoding('utf8');
srv.stdout.on('data', (chunk) => {
  rbuf += chunk;
  let nl;
  while ((nl = rbuf.indexOf('\n')) >= 0) {
    const line = rbuf.slice(0, nl).trim();
    rbuf = rbuf.slice(nl + 1);
    if (!line) continue;
    let msg; try { msg = JSON.parse(line); } catch { continue; }
    if (msg.id != null && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  }
});

function rpc(method, params) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const to = setTimeout(() => reject(new Error(`timeout: ${method}`)), 90_000);
    pending.set(id, (m) => { clearTimeout(to); resolve(m); });
    srv.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  });
}
async function callTool(name, args) {
  const m = await rpc('tools/call', { name, arguments: args || {} });
  const text = m.result?.content?.[0]?.text ?? '';
  let json = null;
  if (!m.result?.isError) { try { json = JSON.parse(text); } catch {} }
  return { text, json, isError: !!m.result?.isError };
}

function edgePids() {
  try {
    return execSync(`pgrep -f ${JSON.stringify(PROFILE_DIR)} || true`).toString().trim().split(/\s+/).filter(Boolean);
  } catch { return []; }
}
function listeningSockets(pids) {
  let s = '';
  for (const p of pids) {
    // -a ANDs the selectors: TCP LISTEN sockets belonging to exactly this pid.
    try { s += execSync(`lsof -nP -a -p ${p} -iTCP -sTCP:LISTEN 2>/dev/null || true`).toString(); } catch {}
  }
  return s.trim();
}
function cmdlines(pids) {
  if (!pids.length) return '';
  try { return execSync(`ps -o command= -p ${pids.join(',')} 2>/dev/null || true`).toString(); } catch { return ''; }
}
function frontmostApp() {
  try {
    return execSync(
      `osascript -e 'tell application "System Events" to name of first process whose frontmost is true'`,
      { stdio: ['ignore', 'pipe', 'ignore'] },
    ).toString().trim();
  } catch { return null; }
}

async function main() {
  console.log(`temp dir: ${TMP}`);

  const init = await rpc('initialize', { protocolVersion: '2024-11-05', capabilities: {} });
  ok('initialize returns serverInfo.name=browser', init.result?.serverInfo?.name === 'browser');
  srv.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');

  const tl = await rpc('tools/list', {});
  const names = (tl.result?.tools || []).map((t) => t.name);
  ok('tools/list exposes browser_open', names.includes('browser_open'), JSON.stringify(names));
  ok('no arbitrary-JS/evaluate tool is exposed', !names.some((n) => /eval|exec|script|cdp_send/i.test(n)), JSON.stringify(names));

  const frontBefore = frontmostApp();

  console.log('opening fixture (launches headless Edge)…');
  const open = await callTool('browser_open', { url: FIXTURE_URL, purpose: 'test' });
  ok('browser_open succeeded', !open.isError, open.text.slice(0, 200));
  const handle = open.json?.handle;
  ok('browser_open returned a handle', typeof handle === 'string' && handle.startsWith('tab_'));
  ok('snapshot wrapped as untrusted_page_content', String(open.json?.snapshot).includes('<untrusted_page_content'));
  ok('snapshot carries the untrusted-data warning', String(open.json?.snapshot).includes('not instructions'));

  // ---- SECURITY: no TCP debug port is open on the browser we launched ----
  const pids = edgePids();
  ok('managed Edge process is running', pids.length > 0, `pids=${pids.join(',')}`);
  const socks = listeningSockets(pids);
  ok('Edge opens NO TCP listening socket (no local-process CDP exposure)', socks === '', socks.replace(/\n/g, ' | '));
  const cmds = cmdlines(pids);
  ok('Edge has NO --remote-debugging-port in its command line', !/--remote-debugging-port(?!=?pipe)/.test(cmds) && !/--remote-debugging-port=\d/.test(cmds),
    (cmds.match(/--remote-debugging-\S+/g) || []).join(' '));
  ok('no cdp.json port file is published', !fs.existsSync(path.join(STATE_DIR, 'cdp.json')));

  // ---- SECURITY: prompt injection in the page cannot forge the delimiter ----
  const snap = await callTool('browser_snapshot', { handle });
  const snapText = String(snap.json?.snapshot || '');
  const inner = snapText.slice(snapText.indexOf('<untrusted_page_content'), snapText.lastIndexOf('</untrusted_page_content>'));
  ok('forged closing delimiter from page is neutralized',
    !inner.includes('</untrusted_page_content>') && snapText.includes('‹/untrusted_page_content'));
  ok('exactly one real closing delimiter', (snapText.match(/<\/untrusted_page_content>/g) || []).length === 1);

  // ---- "without surfacing": Edge must not be frontmost ----
  const frontAfter = frontmostApp();
  if (frontAfter) ok('headless mode did not surface Edge to the foreground', frontAfter !== 'Microsoft Edge', `frontmost=${frontAfter} (before=${frontBefore})`);
  else console.log('  … frontmost check skipped (osascript unavailable)');

  // ---- functional: type / click / scroll / screenshot ----
  ok('browser_type succeeded', !(await callTool('browser_type', { handle, selector: '#name', text: 'hosea' })).isError);
  ok('browser_click succeeded', !(await callTool('browser_click', { handle, selector: '#go' })).isError);
  const snap2 = await callTool('browser_snapshot', { handle, selector: '#out' });
  ok('click handler ran (out shows clicked:hosea)', String(snap2.json?.snapshot).includes('clicked:hosea'), String(snap2.json?.snapshot).slice(0, 160));
  const scroll = await callTool('browser_scroll', { handle, direction: 'bottom' });
  ok('browser_scroll reports at_bottom', scroll.json?.at_bottom === true);
  const shot = await callTool('browser_screenshot', { handle });
  ok('browser_screenshot wrote a PNG', !shot.isError && fs.existsSync(shot.json?.screenshot_path) && shot.json?.bytes > 1000, shot.text.slice(0, 160));
  if (shot.json?.screenshot_path) {
    ok('screenshot file is private (0600)', (fs.statSync(shot.json.screenshot_path).mode & 0o777) === 0o600);
    try { fs.rmSync(shot.json.screenshot_path, { force: true }); } catch {}
  }

  // ---- ownership / listing / adopt ----
  const list = await callTool('browser_list_tabs', {});
  const mine = (list.json?.tabs || []).find((t) => t.handle === handle);
  ok('browser_list_tabs shows our tab owned by me', mine && mine.owner === 'me', JSON.stringify(mine));
  const attach = await callTool('browser_attach_tab', { purpose: 'adopt', url_contains: 'fixture.html' });
  ok('browser_attach_tab adopts an existing tab', !attach.isError && typeof attach.json?.handle === 'string', attach.text.slice(0, 160));

  // ---- status ----
  const status = await callTool('browser_status', {});
  ok('browser_status: transport is pipe', status.json?.transport === 'pipe', JSON.stringify(status.json?.transport));
  ok('browser_status: tcp_port is null', status.json?.tcp_port === null);
  ok('browser_status: headless true', status.json?.headless === true);
  ok('browser_status: connected true', status.json?.connected === true);

  // ---- input validation ----
  const bad = await callTool('browser_open', { url: 'javascript:alert(1)', purpose: 'x' });
  ok('dangerous url scheme rejected', bad.isError && /unsupported url scheme/i.test(bad.text), bad.text.slice(0, 120));

  // ---- release ----
  const rel = await callTool('browser_release_tab', { handle });
  ok('browser_release_tab releases/closes our tab', !rel.isError && rel.json?.released === true, rel.text.slice(0, 160));

  console.log(`\n${pass} passed, ${fail} failed`);
}

async function cleanup() {
  const pids = edgePids();
  try { srv.stdin.end(); } catch {}
  try { srv.kill('SIGTERM'); } catch {}
  await new Promise((r) => setTimeout(r, 800));
  for (const p of pids) { try { process.kill(Number(p), 'SIGKILL'); } catch {} }
  try { fs.rmSync(TMP, { recursive: true, force: true }); } catch {}
}

main()
  .catch((e) => { console.error('TEST HARNESS ERROR:', e); fail++; })
  .finally(async () => { await cleanup(); process.exit(fail ? 1 : 0); });
