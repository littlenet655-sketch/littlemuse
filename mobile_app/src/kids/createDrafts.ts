import AsyncStorage from '@react-native-async-storage/async-storage';
import { File } from 'expo-file-system';
import type { PickedMedia } from './postMedia';

export type CreateDraftKind = 'post' | 'reel' | 'story';

export interface CreateDraft {
  version: 1;
  kind: CreateDraftKind;
  caption: string;
  tags: string;
  location: string;
  contentCategory: string;
  commentsEnabled: boolean;
  storyMusicId: number | null;
  musicStart: number;
  musicDuration: number;
  media: PickedMedia | null;
  updatedAt: number;
}

const keyFor = (userId: number, kind: CreateDraftKind) => `littlemuse:create-draft:v1:${userId}:${kind}`;

export function normalizeCreateDraft(value: unknown, kind: CreateDraftKind): CreateDraft | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Partial<CreateDraft>;
  if (raw.version !== 1 || raw.kind !== kind) return null;
  const media = raw.media && typeof raw.media === 'object'
    && typeof raw.media.uri === 'string'
    && typeof raw.media.fileName === 'string'
    && typeof raw.media.mimeType === 'string'
      ? raw.media as PickedMedia
      : null;
  return {
    version: 1,
    kind,
    caption: typeof raw.caption === 'string' ? raw.caption : '',
    tags: typeof raw.tags === 'string' ? raw.tags : '',
    location: typeof raw.location === 'string' ? raw.location : '',
    contentCategory: typeof raw.contentCategory === 'string' ? raw.contentCategory : '',
    commentsEnabled: raw.commentsEnabled !== false,
    storyMusicId: Number.isInteger(Number(raw.storyMusicId)) && Number(raw.storyMusicId) > 0 ? Number(raw.storyMusicId) : null,
    musicStart: Math.max(0, Number(raw.musicStart) || 0),
    musicDuration: Math.max(1, Math.min(60, Number(raw.musicDuration) || 30)),
    media,
    updatedAt: Number.isFinite(Number(raw.updatedAt)) ? Number(raw.updatedAt) : 0,
  };
}

function mediaStillExists(media: PickedMedia | null): PickedMedia | null {
  if (!media) return null;
  try {
    const file = new File(media.uri);
    return file.exists ? media : null;
  } catch {
    // Some Android content providers cannot be synchronously re-opened after a
    // process restart. Restore the text draft but require the child to re-pick
    // the media instead of showing a broken preview.
    return null;
  }
}

export async function loadCreateDraft(userId: number, kind: CreateDraftKind): Promise<CreateDraft | null> {
  try {
    const raw = await AsyncStorage.getItem(keyFor(userId, kind));
    if (!raw) return null;
    const parsed = normalizeCreateDraft(JSON.parse(raw), kind);
    return parsed ? { ...parsed, media: mediaStillExists(parsed.media) } : null;
  } catch {
    return null;
  }
}

export async function saveCreateDraft(userId: number, draft: CreateDraft): Promise<void> {
  await AsyncStorage.setItem(keyFor(userId, draft.kind), JSON.stringify(draft));
}

export async function clearCreateDraft(userId: number, kind: CreateDraftKind): Promise<void> {
  await AsyncStorage.removeItem(keyFor(userId, kind));
}

export function draftHasContent(draft: Pick<CreateDraft, 'caption' | 'tags' | 'location' | 'musicId' | 'media'>): boolean {
  return Boolean(draft.media || draft.caption.trim() || draft.tags.trim() || draft.location.trim() || draft.musicId);
}
