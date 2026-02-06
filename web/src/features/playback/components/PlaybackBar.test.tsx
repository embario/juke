import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PlaybackBar from './PlaybackBar';

const mockUsePlayback = vi.fn();
const mockSeek = vi.fn();

vi.mock('../hooks/usePlayback', () => ({
  __esModule: true,
  default: () => mockUsePlayback(),
}));

describe('PlaybackBar', () => {
  beforeEach(() => {
    mockSeek.mockReset();
    mockUsePlayback.mockReset();
    mockUsePlayback.mockReturnValue({
      state: {
        provider: 'spotify',
        is_playing: true,
        progress_ms: 12000,
        track: {
          id: 'track-123',
          uri: 'spotify:track:track-123',
          name: 'Cherry Waves',
          duration_ms: 258000,
          artwork_url: 'https://images.example/cherry.jpg',
          album: {
            id: 'album-123',
            uri: 'spotify:album:album-123',
            name: 'Saturday Night Wrist',
          },
          artists: [
            { id: 'artist-1', uri: 'spotify:artist:artist-1', name: 'Deftones' },
          ],
        },
        device: { id: 'device-1', name: 'Web Player' },
      },
      error: null,
      isBusy: false,
      isPlaying: true,
      canControl: true,
      activeTrackUri: 'spotify:track:track-123',
      playTrack: vi.fn(),
      playContext: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      next: vi.fn(),
      previous: vi.fn(),
      seek: mockSeek,
      refresh: vi.fn(),
    });
  });

  it('links track, album, artwork, and artists to catalog detail deep links', () => {
    render(
      <MemoryRouter>
        <PlaybackBar />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: 'Cherry Waves' })).toHaveAttribute('href', '/?open=album&sid=album-123');
    expect(screen.getByRole('link', { name: 'Saturday Night Wrist' })).toHaveAttribute('href', '/?open=album&sid=album-123');
    expect(screen.getByRole('link', { name: 'Deftones' })).toHaveAttribute('href', '/?open=artist&sid=artist-1');
    expect(screen.getByRole('link', { name: /open saturday night wrist detail/i })).toHaveAttribute(
      'href',
      '/?open=album&sid=album-123',
    );
  });

  it('supports scrubbing playback position', () => {
    render(
      <MemoryRouter>
        <PlaybackBar />
      </MemoryRouter>,
    );

    const slider = screen.getByRole('slider', { name: /scrub playback position/i });
    fireEvent.pointerDown(slider);
    fireEvent.change(slider, { target: { value: '42000' } });
    fireEvent.pointerUp(slider, { target: { value: '42000' } });

    expect(mockSeek).toHaveBeenCalledWith(42000);
  });
});
