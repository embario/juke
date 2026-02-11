import { describe, expect, it } from 'vitest';
import { buildTrackPlaybackRequest } from './PlaybackProvider';

describe('buildTrackPlaybackRequest', () => {
  it('builds standalone track playback payload without context', () => {
    expect(buildTrackPlaybackRequest('spotify', 'spotify:track:track-1')).toEqual({
      provider: 'spotify',
      track_uri: 'spotify:track:track-1',
    });
  });

  it('builds context playback payload with track offset', () => {
    expect(
      buildTrackPlaybackRequest(
        'spotify',
        'spotify:track:track-2',
        'spotify:album:album-1',
      ),
    ).toEqual({
      provider: 'spotify',
      context_uri: 'spotify:album:album-1',
      offset_uri: 'spotify:track:track-2',
    });
  });
});
