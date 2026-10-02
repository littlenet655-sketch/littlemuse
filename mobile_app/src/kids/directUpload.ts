import { File, UploadType } from 'expo-file-system';

/** Native binary upload to the v2 presigned URL; media never enters JS memory. */

export interface SignedUploadCallbacks {
  /** Progress updates in bytes; prefer the onProgress option for smooth bars. */
  onProgress?: (bytesSent: number, totalBytes: number) => void;
  /** Aborting rejects the upload with an UploadCancelledError. */
  signal?: AbortSignal;
}

/** Thrown when the user (or a navigation) cancels an in-flight R2 upload. */
export class UploadCancelledError extends Error {
  readonly code = 'upload_cancelled';
  constructor() {
    super('Upload cancelled.');
    this.name = 'UploadCancelledError';
  }
}

export function isUploadCancelled(error: unknown): boolean {
  if (error instanceof UploadCancelledError) return true;
  if (error instanceof DOMException && error.name === 'AbortError') return true;
  const err = error as { name?: string; code?: string } | null;
  return err?.name === 'AbortError' || err?.code === 'upload_cancelled';
}

/**
 * PUT the local file directly to the presigned R2 quarantine URL.
 * Uses an upload task so callers get byte progress and can cancel; the task
 * is always released to avoid leaking native handles.
 */
export async function putFileToSignedUrl(
  uploadUrl: string,
  localUri: string,
  headers: Record<string, string>,
  callbacks?: SignedUploadCallbacks,
): Promise<void> {
  const task = new File(localUri).createUploadTask(uploadUrl, {
    httpMethod: 'PUT',
    uploadType: UploadType.BINARY_CONTENT,
    headers,
    onProgress: callbacks?.onProgress
      ? ({ bytesSent, totalBytes }) => callbacks.onProgress?.(bytesSent, totalBytes)
      : undefined,
    signal: callbacks?.signal,
  });
  let result;
  try {
    result = await task.uploadAsync();
  } catch (error) {
    if (isUploadCancelled(error)) throw new UploadCancelledError();
    const detail = error instanceof Error && error.message ? ` (${error.message})` : '';
    throw new Error(`Cloudflare upload could not start. Keep the file selected and try again${detail}.`);
  } finally {
    task.release();
  }
  if (result.status < 200 || result.status >= 300) {
    throw new Error(`Cloudflare rejected the upload (status ${result.status}). Keep the file selected and try again.`);
  }
}
