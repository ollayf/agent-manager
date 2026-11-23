// cdp.mjs — own a headless Microsoft Edge over a CDP *pipe* (no TCP port).
//
// Security: playwright launches Edge with --remote-debugging-pipe, so the DevTools channel is
// a pair of inherited file descriptors between this process and Edge. No TCP port is opened,
// so no other local process can reach the browser, and DNS-rebinding has no listener to hit.
// The browser is private to this MCP server process and is torn down when it exits.

import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';
import { PROFILE_DIR, HOME, ensureDirs, log, logError } from './state.mjs';

let context = null;
let browser = null;
let launching = null;

const HARDENING_ARGS = [
  '--no-first-run',
  '--no-default-browser-check',
  '--no-service-autorun',
  '--password-store=basic',       // no macOS Keychain prompt (which would surface a dialog)
  '--disable-sync',
  '--disable-background-networking',
  '--disable-features=Translate',
  '--hide-crash-restore-bubble',
];

const headful = () => process.env.CLAUDE_BROWSER_HEADFUL === '1';

// If a previous Edge crashed, its profile SingletonLock may linger. Remove it only when the
// recorded pid is truly dead, so we never steal a lock from a live browser.
function clearStaleSingletonLock() {
  const lock = path.join(PROFILE_DIR, 'SingletonLock');
  try {
    const target = fs.readlinkSync(lock); // e.g. "hostname-12345"
    const pid = Number(String(target).split('-').pop());
    if (Number.isInteger(pid) && pid > 0) {
      try { process.kill(pid, 0); return; } // alive (or EPERM) — leave it
      catch (e) { if (e.code === 'EPERM') return; }
    }
    fs.rmSync(lock, { force: true });
  } catch { /* no lock, or not a symlink — nothing to do */ }
}

async function doLaunch() {
  ensureDirs();
  const opts = {
    headless: !headful(),
    channel: 'msedge',
    args: HARDENING_ARGS,
    acceptDownloads: true,
    downloadsPath: path.join(HOME, 'Downloads'),
    viewport: { width: 1440, height: 900 },
    chromiumSandbox: true,
  };
  let ctx;
  try {
    ctx = await chromium.launchPersistentContext(PROFILE_DIR, opts);
  } catch (e) {
    const msg = String(e?.message || e);
    if (/ProcessSingleton|SingletonLock|profile.*in use|already running|existing browser/i.test(msg)) {
      clearStaleSingletonLock();
      try {
        ctx = await chromium.launchPersistentContext(PROFILE_DIR, opts);
      } catch (e2) {
        logError('browser busy', String(e2?.message || e2).split('\n')[0]);
        const er = new Error('another browser instance is using the profile; close it or run browser_restart');
        er.code = 'E_BROWSER_BUSY';
        throw er;
      }
    } else {
      logError('launch failed', msg.split('\n')[0]);
      throw e;
    }
  }
  context = ctx;
  browser = ctx.browser();
  ctx.on('close', () => { context = null; browser = null; });
  log('edge launched over pipe', { headless: !headful() });
  return ctx;
}

export async function getContext() {
  if (context) return { context, browser };
  if (!launching) launching = doLaunch().finally(() => { launching = null; });
  await launching;
  return { context, browser };
}

export function isConnected() {
  if (!context) return false;
  try { return browser ? browser.isConnected() : true; } catch { return false; }
}

const DROP_PATTERNS = [
  'Target page, context or browser has been closed',
  'browser has been closed',
  'Target closed',
  'has been closed',
];
export async function withReconnect(fn) {
  try {
    return await fn(await getContext());
  } catch (e) {
    const msg = String(e?.message || e);
    if (DROP_PATTERNS.some((p) => msg.includes(p)) && !isConnected()) {
      context = null; browser = null;
      return await fn(await getContext());
    }
    throw e;
  }
}

export async function disconnect() {
  try { if (context) await context.close(); } catch {}
  context = null; browser = null;
}

export async function restart() {
  const started = Date.now();
  await disconnect();
  const { context: ctx } = await getContext();
  return { restarted: true, took_ms: Date.now() - started, pages: ctx ? ctx.pages().length : 0 };
}

export function info() {
  return {
    transport: 'pipe',
    tcp_port: null,
    headless: !headful(),
    connected: isConnected(),
    pages: context ? context.pages().length : 0,
  };
}
