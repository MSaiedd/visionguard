import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, request, setToken, upload } from './api';
afterEach(() => {
  vi.unstubAllGlobals();
  setToken('');
});
describe('workspace transport', () => {
  it('keeps scoped identity in Authorization and parses structured API results', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ total: 3 }), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    setToken('organization-token');
    expect(await api('/inspections')).toEqual({ total: 3 });
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer organization-token');
  });
  it('surfaces optimistic review conflicts', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: 'This review changed in another session',
          }),
          { status: 409 },
        ),
      ),
    );
    await expect(api('/inspections/id/review', 'PATCH', { revision: 0 })).rejects.toThrow(
      'changed in another session',
    );
  });
  it('does not claim success when the server is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('unavailable', { status: 503 })));
    await expect(request('/inspections')).rejects.toThrow('Request failed');
  });
  it('sends image bytes as multipart with a named batch', async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'one', state: 'queued' }), {
        status: 202,
      }),
    );
    vi.stubGlobal('fetch', fetch);
    const result = await upload(
      new File(['bytes'], 'capture.png', { type: 'image/png' }),
      'Batch A',
    );
    expect(result.state).toBe('queued');
    const form = fetch.mock.calls[0][1].body as FormData;
    expect(form.get('batch')).toBe('Batch A');
    expect((form.get('file') as File).name).toBe('capture.png');
  });
});
