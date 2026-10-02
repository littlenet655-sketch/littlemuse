import { CameraView } from 'expo-camera';
import type { CameraViewProps } from 'expo-camera';
import { VideoView } from 'expo-video';
import type { VideoViewProps } from 'expo-video';
import type { ComponentType, ForwardRefExoticComponent, RefAttributes } from 'react';

/**
 * Expo SDK 57 ships these native classes with declarations that strict JSX
 * checking does not recognize as valid React components. Keep the runtime
 * exports unchanged while retaining the package-provided prop and ref types.
 */
export const NativeCameraView = CameraView as unknown as ForwardRefExoticComponent<
  CameraViewProps & RefAttributes<CameraView>
>;

export const NativeVideoView = VideoView as unknown as ComponentType<VideoViewProps>;
