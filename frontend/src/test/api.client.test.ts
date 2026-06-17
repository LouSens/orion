/**
 * Unit tests for the API client (src/api/client.ts).
 *
 * Strategy: mock global.fetch with vi.fn() so no real HTTP requests are made.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearHistory,
  deleteClaim,
  fetchLedger,
  parseDocument,
  submitClaim,
} from '../api/client';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(data: unknown, status = 200, ok = true) {
  const response = {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: vi.fn().mockResolvedValue(data),
    text: vi.fn().mockResolvedValue(JSON.stringify(data)),
  };
  return vi.fn().mockResolvedValue(response);
}

function mockFetchError(status: number, body = 'Server Error') {
  const response = {
    ok: false,
    status,
    statusText: body,
    json: vi.fn().mockRejectedValue(new Error('not json')),
    text: vi.fn().mockResolvedValue(body),
  };
  return vi.fn().mockResolvedValue(response);
}

// ---------------------------------------------------------------------------
// fetchLedger
// ---------------------------------------------------------------------------

describe('fetchLedger()', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns records on success', async () => {
    const payload = { records: [{ claim_id: 'CLM-001', decision: 'auto_approve' }] };
    global.fetch = mockFetch(payload);

    const result = await fetchLedger();
    expect(result.records).toHaveLength(1);
    expect(result.records[0].claim_id).toBe('CLM-001');
  });

  it('calls GET /api/ledger', async () => {
    global.fetch = mockFetch({ records: [] });
    await fetchLedger();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ledger'),
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it('throws on HTTP error', async () => {
    global.fetch = mockFetchError(500, 'Internal Server Error');
    await expect(fetchLedger()).rejects.toThrow('API Error 500');
  });
});

// ---------------------------------------------------------------------------
// submitClaim
// ---------------------------------------------------------------------------

describe('submitClaim()', () => {
  const validRequest = {
    employee_id: 'E001',
    employee_name: 'Alice Tan',
    employee_team: 'Engineering',
    free_text: 'Notion monthly subscription MYR 42',
    receipt_text: 'Total: MYR 42.00',
    attachments: [],
  };

  afterEach(() => vi.restoreAllMocks());

  it('sends POST with JSON body', async () => {
    global.fetch = mockFetch({ claim_id: 'CLM-XYZ', decision: 'auto_approve' });
    await submitClaim(validRequest);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/submit'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(validRequest),
      }),
    );
  });

  it('returns claim_id from response', async () => {
    global.fetch = mockFetch({ claim_id: 'CLM-ABC', decision: 'auto_approve' });
    const result = await submitClaim(validRequest);
    expect(result.claim_id).toBe('CLM-ABC');
  });

  it('throws on 422 (validation error)', async () => {
    global.fetch = mockFetchError(422, 'Unprocessable Entity');
    await expect(submitClaim(validRequest)).rejects.toThrow('API Error 422');
  });

  it('throws on 429 (rate limit)', async () => {
    global.fetch = mockFetchError(429, 'Rate limit exceeded');
    await expect(submitClaim(validRequest)).rejects.toThrow('API Error 429');
  });

  it('throws on 401 (missing API key)', async () => {
    global.fetch = mockFetchError(401, 'API key required');
    await expect(submitClaim(validRequest)).rejects.toThrow('API Error 401');
  });

  it('throws on 403 (invalid API key)', async () => {
    global.fetch = mockFetchError(403, 'Invalid API key');
    await expect(submitClaim(validRequest)).rejects.toThrow('API Error 403');
  });
});

// ---------------------------------------------------------------------------
// deleteClaim
// ---------------------------------------------------------------------------

describe('deleteClaim()', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls DELETE /api/ledger/{claim_id}', async () => {
    global.fetch = mockFetch({ deleted: 'CLM-001' });
    await deleteClaim('CLM-001');

    const calledUrl: string = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(calledUrl).toContain('/api/ledger/CLM-001');
    expect((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1]).toMatchObject({ method: 'DELETE' });
  });

  it('URL-encodes claim IDs with special characters', async () => {
    global.fetch = mockFetch({ deleted: 'CLM-A/B' });
    await deleteClaim('CLM-A/B');
    const calledUrl: string = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(calledUrl).toContain('CLM-A%2FB');
  });

  it('throws on 404', async () => {
    global.fetch = mockFetchError(404, 'Not found');
    await expect(deleteClaim('MISSING')).rejects.toThrow('API Error 404');
  });
});

// ---------------------------------------------------------------------------
// clearHistory
// ---------------------------------------------------------------------------

describe('clearHistory()', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls DELETE /api/ledger with no params when no employeeId', async () => {
    global.fetch = mockFetch({ removed: 5 });
    await clearHistory();
    const calledUrl: string = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(calledUrl).toMatch(/\/api\/ledger$/);
  });

  it('appends employee_id query param when provided', async () => {
    global.fetch = mockFetch({ removed: 2 });
    await clearHistory('E003');
    const calledUrl: string = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(calledUrl).toContain('employee_id=E003');
  });
});

// ---------------------------------------------------------------------------
// parseDocument
// ---------------------------------------------------------------------------

describe('parseDocument()', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends multipart/form-data POST', async () => {
    global.fetch = mockFetch({ text: 'Extracted receipt text', page_count: 1 });
    const file = new File(['dummy pdf content'], 'receipt.pdf', { type: 'application/pdf' });
    const result = await parseDocument(file);
    expect(result.text).toBe('Extracted receipt text');

    const calledUrl: string = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(calledUrl).toContain('/api/parse-document');
    // Should NOT set Content-Type header manually (browser sets boundary)
    const options = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(options.headers).toBeUndefined();
  });

  it('throws on 413 (file too large)', async () => {
    global.fetch = mockFetchError(413, 'File too large');
    const file = new File(['x'], 'big.pdf', { type: 'application/pdf' });
    await expect(parseDocument(file)).rejects.toThrow('API Error 413');
  });

  it('throws on 415 (unsupported type)', async () => {
    global.fetch = mockFetchError(415, 'Unsupported media type');
    const file = new File(['x'], 'image.jpg', { type: 'image/jpeg' });
    await expect(parseDocument(file)).rejects.toThrow('API Error 415');
  });
});
