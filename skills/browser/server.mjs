#!/usr/bin/env node
// server.mjs — stdio MCP server for the browser skill.
// stdout carries only newline-delimited JSON-RPC. All logs go to files.

import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

import {
  SESSION_ID, LIMITS, ensureDirs, getMode, setMode, log, logError, getLastError,
} from './lib/state.mjs';
import { restart as cdpRestart, info as cdpInfo } from './lib/cdp.mjs';
import * as tabs from './lib/tabs.mjs';
import { wrapUntrusted } from './lib/sanitize.mjs';

const SERVER_VERSION = '0.1.0';
ensureDirs();

// ---------------------------------------------------------------- helpers

function toolError(code, message) {
  const e = new Error(message);
  e.code = code;
  return e;
}

async function snapshot(page, selector, maxChars) {
  const sel = selector && String(selector).trim() ? String(selector) : 'body';
  const loc = page.locator(sel).first();
  let text;
  try {
    text = await loc.ariaSnapshot({ timeout: LIMITS.actionTimeoutMs });
  } catch {
    text = await page.innerText('body').catch(() => '');
  }
  let truncated = false;
  const cap = Number.isInteger(maxChars) && maxChars > 0 ? Math.min(maxChars, LIMITS.maxChars) : LIMITS.maxChars;
  if (text.length > cap) { text = text.slice(0, cap); truncated = true; }
  return { text, truncated };
}

const LOGIN_RE = /(\/login|\/signin|\/sign-in|\/auth|\/sso|accounts\.google\.com|login\.microsoftonline\.com)/i;
function ssoNote(requestedUrl, finalUrl, snapText) {
  if (finalUrl !== requestedUrl && (LOGIN_RE.test(finalUrl) || /sign.?in|log.?in|authenticate/i.test(snapText))) {
    return 'sso_blocked: the page redirected to a sign-in flow. Use browser_show so the user can sign in, then retry in the same tab.';
  }
  return null;
}

async function pageResult(handle, extra = {}) {
  const { page, entry } = await tabs.resolve(handle);
  const url = page.url();
  const title = await page.title().catch(() => '');
  return {
    handle,
    purpose: entry?.purpose ?? null,
    title,
    url,
    ...extra,
    page, // internal, stripped before sending
  };
}

function strip(obj) {
  const { page, ...rest } = obj;
  return rest;
}

// ---------------------------------------------------------------- tools

const TOOLS = {
  browser_open: {
    description:
      'Open a URL in a new background tab (quiet: never raises the window) and return an aria snapshot. ' +
      'Returns a handle; pass it to other browser_* tools.',
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string', description: 'http(s), file, or about URL' },
        purpose: { type: 'string', description: 'short reason you are opening this tab' },
        selector: { type: 'string', description: 'optional CSS/text selector to scope the snapshot' },
        max_chars: { type: 'integer' },
      },
      required: ['url'],
    },
    handler: async (a) => {
      const acq = await tabs.acquire({ purpose: a.purpose || 'browse', url: a.url });
      const { page, entry } = await tabs.resolve(acq.handle);
      const snap = await snapshot(page, a.selector, a.max_chars);
      const url = page.url();
      const note = ssoNote(tabs.validateUrl(a.url), url, snap.text);
      return {
        handle: acq.handle,
        purpose: entry?.purpose ?? null,
        title: await page.title().catch(() => ''),
        url,
        ...(note ? { sso_blocked: true, note } : {}),
        snapshot: wrapUntrusted(url, snap.text, snap.truncated),
      };
    },
  },

  browser_snapshot: {
    description: 'Return a fresh aria snapshot of a tab (untrusted page data).',
    inputSchema: {
      type: 'object',
      properties: {
        handle: { type: 'string' },
        selector: { type: 'string' },
        max_chars: { type: 'integer' },
      },
      required: ['handle'],
    },
    handler: async (a) => {
      const { page } = await tabs.resolve(a.handle);
      const snap = await snapshot(page, a.selector, a.max_chars);
      const url = page.url();
      return {
        handle: a.handle,
        url,
        title: await page.title().catch(() => ''),
        snapshot: wrapUntrusted(url, snap.text, snap.truncated),
      };
    },
  },

  browser_click: {
    description: 'Click the first element matching a CSS or text= selector.',
    inputSchema: {
      type: 'object',
      properties: {
        handle: { type: 'string' },
        selector: { type: 'string', description: 'CSS selector or playwright engine selector (e.g. text=Submit)' },
        timeout_ms: { type: 'integer' },
      },
      required: ['handle', 'selector'],
    },
    handler: async (a) => {
      if (!a.selector || typeof a.selector !== 'string') throw toolError('E_BAD_ARG', 'selector is required');
      const { page } = await tabs.resolve(a.handle);
      const timeout = Number.isInteger(a.timeout_ms) ? a.timeout_ms : LIMITS.actionTimeoutMs;
      try {
        await page.locator(a.selector).first().click({ timeout });
      } catch (e1) {
        try {
          await page.getByText(a.selector, { exact: false }).first().click({ timeout });
        } catch (e2) {
          throw toolError('E_CLICK', `${String(e1.message).split('\n')[0]} | ${String(e2.message).split('\n')[0]}`);
        }
      }
      await page.waitForTimeout(200);
      const snap = await snapshot(page, null, null);
      const url = page.url();
      return { handle: a.handle, url, snapshot: wrapUntrusted(url, snap.text, snap.truncated) };
    },
  },

  browser_type: {
    description: 'Fill text into the first element matching a selector; optionally press Enter.',
    inputSchema: {
      type: 'object',
      properties: {
        handle: { type: 'string' },
        selector: { type: 'string' },
        text: { type: 'string' },
        submit: { type: 'boolean' },
      },
      required: ['handle', 'selector', 'text'],
    },
    handler: async (a) => {
      if (typeof a.text !== 'string') throw toolError('E_BAD_ARG', 'text is required');
      const { page } = await tabs.resolve(a.handle);
      const loc = page.locator(a.selector).first();
      await loc.fill(a.text, { timeout: LIMITS.actionTimeoutMs }).catch((e) => {
        throw toolError('E_TYPE', String(e.message).split('\n')[0]);
      });
      if (a.submit) await loc.press('Enter').catch(() => {});
      await page.waitForTimeout(200);
      const snap = await snapshot(page, null, null);
      const url = page.url();
      return { handle: a.handle, url, snapshot: wrapUntrusted(url, snap.text, snap.truncated) };
    },
  },

  browser_screenshot: {
    description: 'Capture a PNG of a tab to a temp file (never raises the window). Returns the file path.',
    inputSchema: {
      type: 'object',
      properties: { handle: { type: 'string' }, full_page: { type: 'boolean' } },
      required: ['handle'],
    },
    handler: async (a) => {
      const { page } = await tabs.resolve(a.handle);
      const file = path.join(os.tmpdir(), `claude-browser-${crypto.randomUUID()}.png`);
      await page.screenshot({ path: file, fullPage: !!a.full_page });
      try { fs.chmodSync(file, 0o600); } catch {}
      const bytes = fs.statSync(file).size;
      return {
        handle: a.handle,
        url: page.url(),
        screenshot_path: file,
        bytes,
        capture_method: 'surface',
        possibly_blank: bytes < 5000,
      };
    },
  },

  browser_scroll: {
    description: 'Scroll a tab (down|up|top|bottom). Returns scroll metrics and a fresh snapshot.',
    inputSchema: {
      type: 'object',
      properties: {
        handle: { type: 'string' },
        direction: { type: 'string', enum: ['down', 'up', 'top', 'bottom'] },
        amount: { type: 'integer' },
      },
      required: ['handle'],
    },
    handler: async (a) => {
      const direction = ['down', 'up', 'top', 'bottom'].includes(a.direction) ? a.direction : 'down';
      const amount = Number.isInteger(a.amount) && a.amount > 0 ? a.amount : 0;
      const { page } = await tabs.resolve(a.handle);
      const m = await page.evaluate(({ direction, amount }) => {
        const el = document.scrollingElement || document.documentElement;
        const step = amount || Math.round(el.clientHeight * 0.85);
        if (direction === 'top') el.scrollTo(0, 0);
        else if (direction === 'bottom') el.scrollTo(0, el.scrollHeight);
        else if (direction === 'up') el.scrollBy(0, -step);
        else el.scrollBy(0, step);
        return { scroll_top: el.scrollTop, scroll_height: el.scrollHeight, client_height: el.clientHeight };
      }, { direction, amount });
      await page.waitForTimeout(150);
      const snap = await snapshot(page, null, null);
      const url = page.url();
      return {
        handle: a.handle,
        direction,
        ...m,
        at_top: m.scroll_top <= 2,
        at_bottom: m.scroll_top + m.client_height >= m.scroll_height - 2,
        snapshot: wrapUntrusted(url, snap.text, snap.truncated),
      };
    },
  },

  browser_list_tabs: {
    description: 'List all open tabs with ownership (me | other-session | null).',
    inputSchema: { type: 'object', properties: {} },
    handler: async () => ({ tabs: await tabs.list() }),
  },

  browser_acquire_tab: {
    description: 'Create a new background tab and return its handle, without navigating.',
    inputSchema: {
      type: 'object',
      properties: { purpose: { type: 'string' }, label: { type: 'string' }, url: { type: 'string' } },
      required: ['purpose'],
    },
    handler: async (a) => tabs.acquire({ purpose: a.purpose, label: a.label, url: a.url }),
  },

  browser_attach_tab: {
    description: 'Adopt an already-open tab by target_id or url_contains, without navigating it.',
    inputSchema: {
      type: 'object',
      properties: {
        purpose: { type: 'string' },
        target_id: { type: 'string' },
        url_contains: { type: 'string' },
        force: { type: 'boolean' },
      },
      required: ['purpose'],
    },
    handler: async (a) => tabs.attach(a),
  },

  browser_release_tab: {
    description: 'Release a tab you own; closes it if you created it.',
    inputSchema: {
      type: 'object',
      properties: { handle: { type: 'string' }, close: { type: 'boolean' } },
      required: ['handle'],
    },
    handler: async (a) => tabs.release(a.handle, a.close !== false),
  },

  browser_show: {
    description: 'Bring a tab to the foreground (the only tool that raises the window) — for manual sign-in.',
    inputSchema: { type: 'object', properties: { handle: { type: 'string' } }, required: ['handle'] },
    handler: async (a) => {
      const { page } = await tabs.resolve(a.handle);
      await page.bringToFront().catch(() => {});
      const headful = process.env.CLAUDE_BROWSER_HEADFUL === '1';
      return {
        handle: a.handle,
        shown: headful,
        url: page.url(),
        ...(headful ? {} : { note: 'Browser is headless (default): there is no window to raise. Relaunch with CLAUDE_BROWSER_HEADFUL=1 and browser_restart for interactive sign-in.' }),
      };
    },
  },

  browser_set_mode: {
    description: 'Set quiet (default, never raises) or classic.',
    inputSchema: { type: 'object', properties: { mode: { type: 'string', enum: ['quiet', 'classic'] } }, required: ['mode'] },
    handler: async (a) => {
      const previous = setMode(a.mode);
      return { mode: getMode(), previous };
    },
  },

  browser_status: {
    description: 'Report server/browser health. Never throws.',
    inputSchema: { type: 'object', properties: {} },
    handler: async () => {
      const i = cdpInfo();
      return {
        mode: getMode(),
        session_id: SESSION_ID,
        server_version: SERVER_VERSION,
        transport: i.transport,     // 'pipe' — no TCP port is ever opened
        tcp_port: i.tcp_port,       // always null
        headless: i.headless,
        connected: i.connected,
        open_pages: i.pages,
        my_tabs: tabs.myTabCount(),
        last_error: getLastError(),
      };
    },
  },

  browser_restart: {
    description: 'Kill and relaunch the managed Edge, then reconnect.',
    inputSchema: { type: 'object', properties: {} },
    handler: async () => cdpRestart(),
  },
};

// ---------------------------------------------------------------- JSON-RPC

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}

function reply(id, result) { send({ jsonrpc: '2.0', id, result }); }
function replyError(id, code, message) { send({ jsonrpc: '2.0', id, error: { code, message } }); }

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, rej) => setTimeout(() => rej(toolError('E_TIMEOUT', `call exceeded ${ms}ms`)), ms)),
  ]);
}

async function handle(msg) {
  const { id, method, params } = msg;
  if (method === 'initialize') {
    return reply(id, {
      protocolVersion: '2024-11-05',
      capabilities: { tools: {} },
      serverInfo: { name: 'browser', version: SERVER_VERSION },
    });
  }
  if (method === 'notifications/initialized' || method?.startsWith('notifications/')) return; // no id
  if (method === 'ping') return reply(id, {});
  if (method === 'resources/list') return reply(id, { resources: [] });
  if (method === 'prompts/list') return reply(id, { prompts: [] });
  if (method === 'tools/list') {
    return reply(id, {
      tools: Object.entries(TOOLS).map(([name, t]) => ({
        name, description: t.description, inputSchema: t.inputSchema,
      })),
    });
  }
  if (method === 'tools/call') {
    const name = params?.name;
    const args = params?.arguments ?? {};
    const tool = TOOLS[name];
    if (!tool) return replyError(id, -32601, `unknown tool: ${name}`);
    try {
      const out = await withTimeout(tool.handler(args), LIMITS.callTimeoutMs);
      const clean = out && out.page ? strip(out) : out;
      return reply(id, { content: [{ type: 'text', text: JSON.stringify(clean, null, 2) }] });
    } catch (e) {
      const code = e.code || 'E_ERROR';
      logError(`${name} failed`, `${code}: ${e.message}`);
      return reply(id, { content: [{ type: 'text', text: `Error ${code}: ${e.message}` }], isError: true });
    }
  }
  if (id !== undefined && id !== null) return replyError(id, -32601, `unknown method: ${method}`);
}

// Newline-delimited JSON on stdin.
let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  buf += chunk;
  let nl;
  while ((nl = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, nl).trim();
    buf = buf.slice(nl + 1);
    if (!line) continue;
    let msg;
    try { msg = JSON.parse(line); } catch { continue; }
    Promise.resolve(handle(msg)).catch((e) => {
      logError('handler crashed', String(e?.message || e));
      if (msg?.id != null) replyError(msg.id, -32603, 'internal error');
    });
  }
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
log('server started', { session: SESSION_ID, mode: getMode() });
