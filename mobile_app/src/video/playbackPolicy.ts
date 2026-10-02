import type { BufferOptions } from 'expo-video';
import type { PlaybackPolicy } from './types';

/**
 * Configure short-form video buffering parameters.
 * - NORMAL: Fast ~1.5s startup buffer, 8s forward buffer, bounded memory.
 * - DATA_SAVER: 1.0s startup buffer, 4s forward buffer, conservative bandwidth.
 */
export function getBufferOptions(policy: PlaybackPolicy = 'NORMAL'): BufferOptions {
  if (policy === 'DATA_SAVER') {
    return {
      minBufferForPlayback: 1.0,
      preferredForwardBufferDuration: 4.0,
      prioritizeTimeOverSizeThreshold: true,
    };
  }

  return {
    minBufferForPlayback: 1.5,
    preferredForwardBufferDuration: 8.0,
    prioritizeTimeOverSizeThreshold: true,
  };
}
