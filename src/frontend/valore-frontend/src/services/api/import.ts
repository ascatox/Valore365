import { API_URL, getAuthToken, ApiErrorPayload, apiFetch } from './client';
import type {
  CsvImportPreviewResponse,
  CsvImportCommitResponse,
} from './types';

export const uploadCsvImportPreview = async (
  portfolioId: number,
  file: File,
  broker = 'generic',
): Promise<CsvImportPreviewResponse> => {
  const token = await getAuthToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const formData = new FormData();
  formData.append('file', file);
  formData.append('broker', broker);
  const response = await fetch(`${API_URL}/portfolios/${portfolioId}/csv-import/preview`, {
    method: 'POST',
    headers: { ...authHeaders },
    body: formData,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) message = body.error.message;
    } catch { /* ignore */ }
    throw new Error(message);
  }
  return response.json() as Promise<CsvImportPreviewResponse>;
};

export const downloadCsvImportTemplate = async (
  broker = 'generic',
): Promise<{ blob: Blob; filename: string }> => {
  const token = await getAuthToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${API_URL}/csv-import/template?broker=${encodeURIComponent(broker)}`, {
    method: 'GET',
    headers: { ...authHeaders },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) message = body.error.message;
    } catch { /* ignore */ }
    throw new Error(message);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') || '';
  const filenameMatch = disposition.match(/filename="([^"]+)"/i);
  return {
    blob,
    filename: filenameMatch?.[1] || `valore365-${broker}-import-template.xlsx`,
  };
};

export const commitCsvImport = async (batchId: number): Promise<CsvImportCommitResponse> => {
  return apiFetch<CsvImportCommitResponse>(`/csv-import/${batchId}/commit`, {
    method: 'POST',
  });
};

export const cancelCsvImport = async (batchId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/csv-import/${batchId}`, {
    method: 'DELETE',
  });
};
