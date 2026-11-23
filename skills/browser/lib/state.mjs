// state.mjs — paths, constants, session identity, mode, and file logging.
// Nothing here writes to stdout: stdout is reserved for JSON-RPC.

import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

export const HOME = os.homedir();
// Paths are overridable only for hermetic testing; production always uses ~/.claude.
export const STATE_DIR = process.env.CLAUDE_BROWSER_STATE_DIR?.trim() || path.join(HOME, '.claude', 'browser-state');
export const PROFILE_DIR = process.env.CLAUDE_BROWSER_PROFILE_DIR?.trim() || path.join(HOME, '.claude', 'browser-profile');

export const PATHS = {
  serverLog: path.join(STATE_DIR, 'server.log'),
  navLog: path.join(STATE_DIR, 'nav.log'),
};

export const LIMITS = {
  callTimeoutMs: 120_000,
  connectBudgetMs: 45_000,
  maxChars: 40_000,
  navTimeoutMs: 30_000,
  actionTimeoutMs: 5_000,
  logRotateBytes: 2 * 1024 * 1024,
};

export const SESSION_ID =
  process.env.CLAUDE_CODE_SESSION_ID?.trim() ||
  `pid-${process.pid}-${Date.now()}`;

// Mode: quiet (never raises the window) is the default. Only 'classic' is the alternative.
function normalizeMode(v) {
  const m = (v ?? '').trim().toLowerCase();
  return m === 'classic' ? 'classic' : 'quiet';
}
let MODE = normalizeMode(process.env.CLAUDE_BROWSER_MODE);
export const getMode = () => MODE;
export function setMode(v) {
  const next = (v ?? '').trim().toLowerCase();
  if (next !== 'quiet' && next !== 'classic') {
    const err = new Error(`invalid mode "${v}"; use quiet or classic`);
    err.code = 'E_BAD_MODE';
    throw err;
  }
  const prev = MODE;
  MODE = next;
  return prev;
}

export function ensureDirs() {
  fs.mkdirSync(STATE_DIR, { recursive: true, mode: 0o700 });
  fs.mkdirSync(PROFILE_DIR, { recursive: true, mode: 0o700 });
  try { fs.chmodSync(STATE_DIR, 0o700); } catch {}
  try { fs.chmodSync(PROFILE_DIR, 0o700); } catch {}
}

function rotateIfLarge(file) {
  try {
    const st = fs.statSync(file);
    if (st.size > LIMITS.logRotateBytes) fs.renameSync(file, file + '.1');
  } catch {}
}

function writeLine(file, obj) {
  try {
    rotateIfLarge(file);
    fs.appendFileSync(file, JSON.stringify(obj) + '\n', { mode: 0o600 });
  } catch {
    // Logging must never throw.
  }
}

let lastError = null;
export const getLastError = () => lastError;

export function log(message, detail) {
  writeLine(PATHS.serverLog, { ts: new Date().toISOString(), message, ...(detail ? { detail } : {}) });
}

export function logError(message, detail) {
  lastError = { ts: new Date().toISOString(), message, detail: detail ?? null };
  writeLine(PATHS.serverLog, { ts: lastError.ts, level: 'error', message, ...(detail ? { detail } : {}) });
}

// nav.log records navigations with query/hash stripped so secrets in URLs are not persisted.
export function logNav(url, note) {
  let safe = url;
  try {
    const u = new URL(url);
    u.search = '';
    u.hash = '';
    safe = u.toString();
  } catch {
    safe = String(url).split(/[?#]/)[0];
  }
  writeLine(PATHS.navLog, { ts: new Date().toISOString(), url: safe, ...(note ? { note } : {}) });
}
