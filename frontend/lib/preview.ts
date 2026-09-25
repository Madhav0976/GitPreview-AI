/**
 * Static Preview Client API (GitPreview-AI V2 - Phase 2)
 */

import { getApiBase } from './api';

export interface PreviewDetectResponse {
  status: 'READY' | 'UNSUPPORTED' | 'NEEDS_ENV' | 'NEEDS_EXTERNAL_SERVICE' | 'UNKNOWN' | string;
  category: string;
  entryPoint: string | null;
  previewUrl: string | null;
  totalAssets: number;
  detectedAssets: string[];
  blockers: string[];
}

const PREVIEW_DETECT_TIMEOUT_MS = 30000;

export async function detectPreview(
  repoUrl: string,
  externalSignal?: AbortSignal
): Promise<PreviewDetectResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), PREVIEW_DETECT_TIMEOUT_MS);

  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutId);
      throw new DOMException('Aborted', 'AbortError');
    }
    externalSignal.addEventListener('abort', onExternalAbort, { once: true });
  }

  try {
    const response = await fetch(`${getApiBase()}/preview/detect`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ repoUrl }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Static preview detection failed');
    }

    return await response.json();
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw err;
      }
      throw new Error('Static preview detection timed out. Please try again.');
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener('abort', onExternalAbort);
    }
  }
}

export function resolvePreviewUrl(previewPath: string | null): string {
  if (!previewPath) return '';
  if (previewPath.startsWith('http://') || previewPath.startsWith('https://')) {
    return previewPath;
  }
  // Strip trailing /api to attach the full preview path like /api/preview/...
  const baseOrigin = getApiBase().replace(/\/api\/?$/, '');
  const cleanPath = previewPath.startsWith('/') ? previewPath : `/${previewPath}`;
  return `${baseOrigin}${cleanPath}`;
}

