import { ApiError, buildUrl, extractErrorMessage, LOGOUT_EVENT, request, tokenStore } from './client';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('buildUrl', () => {
  it('prefixes /api/v1 and drops empty query params', () => {
    expect(buildUrl('/experiments/', { status: 'RUNNING', search: '', page: 2 })).toBe('/api/v1/experiments/?status=RUNNING&page=2');
    expect(buildUrl('/healthz', undefined, true)).toBe('/healthz');
  });
});

describe('extractErrorMessage', () => {
  it('flattens DRF error shapes', () => {
    expect(extractErrorMessage({ detail: 'Not found.', status_code: 404 })).toBe('Not found.');
    expect(extractErrorMessage({ non_field_errors: ['Exactly one variant must be marked as control.'], status_code: 400 })).toBe(
      'Exactly one variant must be marked as control.',
    );
    expect(extractErrorMessage({ key: ['This field is required.'] })).toBe('key: This field is required.');
  });
});

describe('request', () => {
  afterEach(() => vi.restoreAllMocks());

  it('refreshes the access token once on 401 and retries', async () => {
    tokenStore.set({ access: 'old', refresh: 'r1' });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockResolvedValueOnce(json(200, { access: 'new' }))
      .mockResolvedValueOnce(json(200, { id: 'me' }));

    await expect(request<{ id: string }>('/auth/me/')).resolves.toEqual({ id: 'me' });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]![0]).toBe('/api/v1/auth/token/refresh/');
    const retryHeaders = (fetchMock.mock.calls[2]![1] as RequestInit).headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBe('Bearer new');
    expect(tokenStore.access).toBe('new');
  });

  it('clears the session and emits logout when refresh fails', async () => {
    tokenStore.set({ access: 'old', refresh: 'bad' });
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockResolvedValueOnce(json(401, { detail: 'invalid refresh' }));
    const onLogout = vi.fn();
    window.addEventListener(LOGOUT_EVENT, onLogout);

    const err = await request('/experiments/').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    expect(tokenStore.access).toBeNull();
    expect(onLogout).toHaveBeenCalledTimes(1);
    window.removeEventListener(LOGOUT_EVENT, onLogout);
  });

  it('surfaces 404 as ApiError.isNotFound', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(404, { detail: 'Not found.' }));
    const err = (await request('/experiments/x/explain/').catch((e: unknown) => e)) as ApiError;
    expect(err.isNotFound).toBe(true);
    expect(err.message).toBe('Not found.');
  });
});
