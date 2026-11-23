// tabs.mjs — tab lifecycle over the server-owned browser context. In-memory, single-session.
// There is no cross-session registry: this server owns its own private Edge, so every tab it
// tracks belongs to it. That removes shared mutable state (and its locking) as an attack and
// bug surface.

import crypto from 'node:crypto';
import { getContext } from './cdp.mjs';
import { logNav } from './state.mjs';

const mem = new Map();               // handle -> { page, purpose, label, origin }
const targetIdCache = new WeakMap(); // Page -> targetId

const newHandle = () => 'tab_' + crypto.randomBytes(6).toString('hex');
function err(code, message) { const e = new Error(`${code}: ${message}`); e.code = code; return e; }

export function validateUrl(url) {
  if (typeof url !== 'string' || !url.trim()) throw err('E_BAD_ARG', 'url is required');
  let u;
  try { u = new URL(url); } catch { throw err('E_BAD_ARG', `not a valid url: ${url}`); }
  if (!['http:', 'https:', 'about:', 'file:'].includes(u.protocol)) {
    throw err('E_BAD_ARG', `unsupported url scheme: ${u.protocol}`);
  }
  return u.toString();
}

async function targetIdOf(context, page) {
  if (targetIdCache.has(page)) return targetIdCache.get(page);
  const s = await context.newCDPSession(page);
  try {
    const { targetInfo } = await s.send('Target.getTargetInfo');
    targetIdCache.set(page, targetInfo.targetId);
    return targetInfo.targetId;
  } finally {
    await s.detach().catch(() => {});
  }
}

async function findByTarget(context, targetId) {
  for (const page of context.pages()) {
    if (page.isClosed()) continue;
    try { if ((await targetIdOf(context, page)) === targetId) return page; } catch {}
  }
  return null;
}

export async function acquire({ purpose, label, url }) {
  if (!purpose || typeof purpose !== 'string') throw err('E_BAD_ARG', 'purpose is required');
  const { context } = await getContext();
  const page = await context.newPage();
  const handle = newHandle();
  mem.set(handle, { page, purpose, label: label || handle, origin: 'created' });
  let nav = null;
  if (url) nav = await navigate(handle, url);
  return { handle, purpose, origin: 'created', created_tab: true, ...(nav ? { url: nav.url, title: nav.title } : {}) };
}

export async function resolve(handle) {
  if (!handle || typeof handle !== 'string') throw err('E_BAD_ARG', 'handle is required');
  const rec = mem.get(handle);
  if (!rec) throw err('E_TAB_GONE', `unknown handle ${handle}`);
  if (rec.page.isClosed()) { mem.delete(handle); throw err('E_TAB_GONE', `tab ${handle} is gone`); }
  return { page: rec.page, rec };
}

export async function navigate(handle, url) {
  const { page } = await resolve(handle);
  const u = validateUrl(url);
  const res = await page.goto(u, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch((e) => {
    throw err('E_NAV', String(e?.message || e).split('\n')[0]);
  });
  const finalUrl = page.url();
  const title = await page.title().catch(() => '');
  logNav(finalUrl);
  return { url: finalUrl, title, status: res?.status?.() ?? null };
}

export async function attach({ target_id, url_contains, purpose }) {
  if (!purpose || typeof purpose !== 'string') throw err('E_BAD_ARG', 'purpose is required');
  if (!target_id && !url_contains) throw err('E_BAD_ARG', 'target_id or url_contains is required');
  const { context } = await getContext();

  let page = null;
  if (url_contains) {
    const ms = context.pages().filter((p) => !p.isClosed() && p.url().includes(url_contains));
    if (ms.length === 0) throw err('E_TAB_GONE', `no open tab whose url contains "${url_contains}"`);
    if (ms.length > 1) throw err('E_AMBIGUOUS', `${ms.length} open tabs match "${url_contains}"`);
    page = ms[0];
  } else {
    page = await findByTarget(context, target_id);
    if (!page) throw err('E_TAB_GONE', `no open tab with target_id ${target_id}`);
  }

  for (const [h, r] of mem) {
    if (r.page === page) return { handle: h, purpose: r.purpose, origin: r.origin, navigated: false, url: page.url() };
  }
  const handle = newHandle();
  mem.set(handle, { page, purpose, label: handle, origin: 'adopted' });
  return { handle, purpose, origin: 'adopted', navigated: false, url: page.url(), title: await page.title().catch(() => '') };
}

export async function release(handle, close = true) {
  const rec = mem.get(handle);
  if (!rec) return { released: false, reason: 'no such tab', handle };
  let closed = false;
  if (close && rec.origin === 'created' && !rec.page.isClosed()) {
    try { await rec.page.close(); closed = true; } catch {}
  }
  mem.delete(handle);
  return { released: true, closed, tab: rec.label, handle };
}

export async function list() {
  const { context } = await getContext();
  const byPage = new Map();
  for (const [h, r] of mem) byPage.set(r.page, { handle: h, purpose: r.purpose, origin: r.origin });
  const out = [];
  for (const page of context.pages()) {
    if (page.isClosed()) continue;
    const known = byPage.get(page);
    out.push({
      url: page.url(),
      title: await page.title().catch(() => ''),
      handle: known?.handle ?? null,
      purpose: known?.purpose ?? null,
      owner: known ? 'me' : null,
      origin: known?.origin ?? null,
    });
  }
  return out;
}

export function myTabCount() {
  let n = 0;
  for (const [, r] of mem) if (!r.page.isClosed()) n++;
  return n;
}
