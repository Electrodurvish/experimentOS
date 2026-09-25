// Low-level HTTP client: JWT storage, automatic refresh on 401, typed errors.

import type { TokenPair } from './types';

export const API_BASE = '/api/v1';

const ACCESS_KEY = 'eos.access';
const REFRESH_KEY = 'eos.refresh';
export const LOGOUT_EVENT = 'eos:logout';

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: tokens live for this page only */
  }
}

export const tokenStore = {
  get access(): string | null {
    return safeGet(ACCESS_KEY);
  },
  get refresh(): string | null {
    return safeGet(REFRESH_KEY);
  },
  set(pair: Partial<TokenPair>): void {
    if (pair.access !== undefined) safeSet(ACCESS_KEY, pair.access);
    if (pair.refresh !== undefined) safeSet(REFRESH_KEY, pair.refresh);
  },
  clear(): void {
    safeSet(ACCESS_KEY, null);
    safeSet(REFRESH_KEY, null);
  },
};

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, fallback?: string) {
    super(extractErrorMessage(body) ?? fallback ?? `Request failed (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

/** Flatten a DRF error body ({detail}, {non_field_errors}, {field: [msg]}) into one line. */
export function extractErrorMessage(body: unknown): string | null {
  if (body == null) return null;
  if (typeof body === 'string') return body.trim() ? body.slice(0, 300) : null;
  if (Array.isArray(body)) {
    const parts = body.map((b) => extractErrorMessage(b)).filter((s): s is string => !!s);
    return parts.length ? parts.join(' ') : null;
  }
  if (typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    if (typeof obj.detail === 'string') return obj.detail;
    const parts: string[] = [];
    for (const [field, value] of Object.entries(obj)) {
      if (field === 'status_code') continue;
      const msg = extractErrorMessage(value);
      if (!msg) continue;
      parts.push(field === 'non_field_errors' || field === 'detail' ? msg : `${field}: ${msg}`);
    }
    return parts.length ? parts.join(' · ') : null;
  }
  return String(body);
}

let refreshInFlight: Promise<boolean> | null = null;

/** Exchange the refresh token for a new access token. Concurrent callers share one request. */
export function refreshAccessToken(): Promise<boolean> {
  const refresh = tokenStore.refresh;
  if (!refresh) return Promise.resolve(false);
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/token/refresh/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ refresh }),
        });
        if (!res.ok) return false;
        const data = (await res.json()) as Partial<TokenPair>;
        if (!data.access) return false;
        tokenStore.set(data);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Skip the Authorization header (used by login and probes). */
  anonymous?: boolean;
  /** Treat `path` as site-root relative (e.g. /healthz) instead of under /api/v1. */
  root?: boolean;
  signal?: AbortSignal;
}

export function buildUrl(path: string, query?: RequestOptions['query'], root = false): string {
  const base = root || path.startsWith('/api/') ? path : `${API_BASE}${path}`;
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue;
    params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

async function parseBody(res: Response): Promise<unknown> {
  if (res.status === 204) return null;
  const text = await res.text();
  if (!text) return null;
  const type = res.headers.get('content-type') ?? '';
  if (type.includes('json')) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  return text;
}

function send(url: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  const access = tokenStore.access;
  if (!opts.anonymous && access) headers.Authorization = `Bearer ${access}`;
  return fetch(url, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
}

/**
 * Perform a request against the API. Paths starting with "/" are resolved under /api/v1
 * unless they already begin with /api/. On 401 the access token is refreshed once and
 * the request retried; if refresh fails the session is cleared and LOGOUT_EVENT fires.
 */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, opts.query, opts.root);
  let res = await send(url, opts);

  if (res.status === 401 && !opts.anonymous) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await send(url, opts);
    }
    if (res.status === 401) {
      tokenStore.clear();
      window.dispatchEvent(new Event(LOGOUT_EVENT));
    }
  }

  const body = await parseBody(res);
  if (!res.ok) throw new ApiError(res.status, body, res.statusText);
  return body as T;
}
