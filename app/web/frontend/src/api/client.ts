/**
 * API client for communicating with the Orion Python backend.
 * Base URL is read from VITE_API_BASE_URL environment variable.
 */

/// <reference types="vite/client" />

import type {
  LedgerResponse,
  ParseDocumentResponse,
  SubmitClaimRequest,
  SubmitClaimResponse,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Base fetch wrapper that handles common request logic,
 * including JSON parsing and error handling.
 */
async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => response.statusText);
    throw new Error(`API Error ${response.status}: ${errorBody}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Fetch the ledger records from GET /api/ledger.
 */
export async function fetchLedger(): Promise<LedgerResponse> {
  return apiFetch<LedgerResponse>('/api/ledger');
}

/**
 * Submit a reimbursement claim to POST /api/submit.
 * The backend processes synchronously and returns the full workflow result.
 */
export async function submitClaim(data: SubmitClaimRequest): Promise<SubmitClaimResponse> {
  return apiFetch<SubmitClaimResponse>('/api/submit', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Delete a single ledger record by claim ID via DELETE /api/ledger/{claim_id}.
 */
export async function deleteClaim(claimId: string): Promise<void> {
  await apiFetch<{ deleted: string }>(`/api/ledger/${encodeURIComponent(claimId)}`, { method: 'DELETE' });
}

/**
 * Clear all ledger records (optionally scoped to one employee) via DELETE /api/ledger.
 */
export async function clearHistory(employeeId?: string): Promise<void> {
  const params = employeeId ? `?employee_id=${encodeURIComponent(employeeId)}` : '';
  await apiFetch<{ removed: number }>(`/api/ledger${params}`, { method: 'DELETE' });
}

/**
 * Upload a document to POST /api/parse-document.
 * Returns the extracted plain text from the file.
 * NOTE: This endpoint accepts multipart/form-data, not JSON.
 */
export async function parseDocument(file: File): Promise<ParseDocumentResponse> {
  const url = `${API_BASE}/api/parse-document`;
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
    // Do NOT set Content-Type — browser sets it with the correct boundary
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => response.statusText);
    throw new Error(`API Error ${response.status}: ${errorBody}`);
  }

  return response.json() as Promise<ParseDocumentResponse>;
}
