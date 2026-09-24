/**
 * Static Preview Client API (GitPreview-AI V2 - Phase 2)
 */

export interface PreviewDetectResponse {
  status: 'READY' | 'UNSUPPORTED' | 'NEEDS_ENV' | 'NEEDS_EXTERNAL_SERVICE' | 'UNKNOWN' | string;
  category: string;
  entryPoint: string | null;
  previewUrl: string | null;
  totalAssets: number;
  detectedAssets: string[];
  blockers: string[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'https://gitpreview-ai-backend.onrender.com/api';

export async function detectPreview(repoUrl: string): Promise<PreviewDetectResponse> {
  const response = await fetch(`${API_BASE}/preview/detect`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ repoUrl }),
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    throw new Error(errData.detail || 'Static preview detection failed');
  }

  return response.json();
}

export function resolvePreviewUrl(previewPath: string | null): string {
  if (!previewPath) return '';
  if (previewPath.startsWith('http://') || previewPath.startsWith('https://')) {
    return previewPath;
  }
  // Strip trailing /api to attach the full preview path like /api/preview/...
  const baseOrigin = API_BASE.replace(/\/api\/?$/, '');
  const cleanPath = previewPath.startsWith('/') ? previewPath : `/${previewPath}`;
  return `${baseOrigin}${cleanPath}`;
}
