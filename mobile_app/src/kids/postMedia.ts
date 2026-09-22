/**
 * Post/reel/story media selection for ordinary creation.
 * Uses normal Expo gallery + camera capture.
 */
import * as ImagePicker from 'expo-image-picker';
import { File } from 'expo-file-system';

// Pure identity/size helpers live in the upload-pipeline API module so they are
// unit-testable without native modules; re-exported here for compatibility.
export { formatBytes, mediaKindFromMimeType, validateMediaIdentity } from '../api/kidsUpload';

export interface PickedMedia {
  uri: string;
  fileName: string;
  mimeType: string;
  fileSize?: number;
  width?: number;
  height?: number;
  duration?: number | null;
}

function extOf(name: string, fallback: string): string {
  const parts = name.split('.');
  return parts.length > 1 ? (parts[parts.length - 1] ?? fallback).toLowerCase() : fallback;
}

export function localMediaSize(uri: string): number {
  const file = new File(uri);
  if (!file.exists || !Number.isSafeInteger(file.size) || file.size <= 0) {
    throw new Error('Could not determine the selected file size. Choose the file again.');
  }
  return file.size;
}

function toPicked(asset: ImagePicker.ImagePickerAsset, kind: 'image' | 'video'): PickedMedia {
  const isVideo = kind === 'video' || asset.type === 'video';
  const ext = extOf(asset.fileName ?? asset.uri, isVideo ? 'mp4' : 'jpg');
  const mimeType = asset.mimeType ?? (isVideo ? 'video/mp4' : ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg');
  return {
    uri: asset.uri,
    fileName: asset.fileName ?? `littlenet.${ext}`,
    mimeType,
    fileSize: asset.fileSize,
    width: asset.width,
    height: asset.height,
    duration: asset.duration ?? null,
  };
}

export async function pickGalleryMedia(kind: 'image' | 'video'): Promise<PickedMedia | null> {
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: kind === 'video' ? ['videos'] : ['images'],
    quality: 0.9,
  });
  if (result.canceled || !result.assets?.[0]) return null;
  return toPicked(result.assets[0], kind);
}

export async function capturePostMedia(kind: 'image' | 'video'): Promise<PickedMedia | null> {
  const camera = await ImagePicker.requestCameraPermissionsAsync();
  if (!camera.granted) throw new Error('Camera access is needed to take a photo or video.');
  const result = await ImagePicker.launchCameraAsync({
    mediaTypes: kind === 'video' ? ['videos'] : ['images'],
    quality: 0.9,
    videoMaxDuration: 60,
  });
  if (result.canceled || !result.assets?.[0]) return null;
  return toPicked(result.assets[0], kind);
}
