import { describe, expect, it } from 'vitest';
import type { Track } from '../catalog/types';
import { deriveTrackUri, hasPlayableUri } from './utils';

const buildTrack = (overrides: Partial<Track> = {}): Track => ({
  id: 1,
  name: 'Test Track',
  album: null,
  duration_ms: 120000,
  track_number: 1,
  explicit: false,
  spotify_id: 'abc123',
  ...overrides,
});

describe('deriveTrackUri', () => {
  it('prefers spotify_data uri when present', () => {
    const track = buildTrack({ spotify_data: { uri: 'spotify:track:from-data' } });
    expect(deriveTrackUri(track)).toBe('spotify:track:from-data');
  });

  it('builds uri from spotify_id when needed', () => {
    const track = buildTrack({ spotify_id: 'xyz789' });
    expect(deriveTrackUri(track)).toBe('spotify:track:xyz789');
  });

  it('returns null when no identifiers are available', () => {
    const track = buildTrack({ spotify_id: '' });
    expect(deriveTrackUri(track)).toBeNull();
    expect(hasPlayableUri(track)).toBe(false);
  });
});
