// Re-export the camera capture contract (CapturedPhoto type, errors, core).
// The concrete camera wiring lives in the screens' CameraCapture component;
// there is intentionally no shared captureLivePhoto() helper here.
export * from './capture';
