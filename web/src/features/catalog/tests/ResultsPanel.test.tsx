import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import ResultsPanel from '../components/ResultsPanel';

vi.mock('../../playback/hooks/usePlayback', () => ({
  usePlayback: () => ({
    state: null,
    error: null,
    isBusy: false,
    isPlaying: false,
    canControl: false,
    activeTrackUri: null,
    playTrack: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    next: vi.fn(),
    previous: vi.fn(),
    refresh: vi.fn(),
  }),
}));

const mockData = {
  genres: [],
  artists: [{ id: 1, name: 'Artist', genres: [], spotify_id: '1' }],
  albums: [
    {
      id: 2,
      name: 'Album',
      artists: [{ id: 1, name: 'Artist', genres: [], spotify_id: '1' }],
      total_tracks: 10,
      release_date: '2023-01-01',
      spotify_id: '2',
    },
  ],
  tracks: [
    {
      id: 3,
      name: 'Track',
      album: 'Album',
      duration_ms: 180000,
      track_number: 1,
      explicit: false,
      spotify_id: '3',
    },
  ],
};

describe('ResultsPanel', () => {
  it('renders lists for each filter', () => {
    render(
      <ResultsPanel
        data={mockData}
        filters={['artists', 'albums', 'tracks']}
        isLoading={false}
        error={null}
      />
    );

    expect(screen.getByText('Artists')).toBeInTheDocument();
    expect(screen.getByText('Albums')).toBeInTheDocument();
    expect(screen.getByText('Tracks')).toBeInTheDocument();
  });
});
