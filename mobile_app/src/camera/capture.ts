/**
 * Testable live-photo core. Camera permission states are distinguished
 * explicitly; gallery selection is never offered (launchCamera only).
 */

export interface CapturedPhoto {
  base64: string;
  width: number;
  height: number;
  /** Temporary native URI for the captured frame. */
  uri?: string;
}

export interface CameraDeps {
  getPermissions: () => Promise<{ granted: boolean; canAskAgain: boolean }>;
  requestPermissions: () => Promise<{ granted: boolean; canAskAgain: boolean }>;
  launchCamera: () => Promise<{ cancelled: boolean; base64?: string; width?: number; height?: number; uri?: string }>;
}

export class CameraCancelledError extends Error {
  constructor() {
    super('Photo was cancelled. Take a live photo to continue.');
    this.name = 'CameraCancelledError';
  }
}

export class CameraPermissionError extends Error {
  constructor() {
    super('Camera access is needed for this safety check. Allow the camera and try again.');
    this.name = 'CameraPermissionError';
  }
}

export class CameraBlockedError extends Error {
  constructor() {
    super('Camera access is permanently denied. Open Settings to allow the camera, then try again.');
    this.name = 'CameraBlockedError';
  }
}

export async function captureLivePhotoCore(deps: CameraDeps): Promise<CapturedPhoto> {
  let current = { granted: false, canAskAgain: true };
  try {
    current = await deps.getPermissions();
  } catch {
    current = { granted: false, canAskAgain: true };
  }
  let granted = current.granted;
  let canAskAgain = current.canAskAgain;
  if (!granted) {
    const requested = await deps.requestPermissions();
    granted = requested.granted;
    canAskAgain = requested.canAskAgain;
  }
  if (!granted) {
    if (canAskAgain) throw new CameraPermissionError();
    throw new CameraBlockedError();
  }
  let shot: { cancelled: boolean; base64?: string; width?: number; height?: number; uri?: string };
  try {
    shot = await deps.launchCamera();
  } catch {
    throw new Error('The camera could not be opened. Please try again.');
  }
  if (shot.cancelled) throw new CameraCancelledError();
  if (!shot.base64) throw new Error('Could not read the camera photo. Please try again.');
  return { base64: shot.base64, width: shot.width ?? 0, height: shot.height ?? 0, uri: shot.uri };
}
