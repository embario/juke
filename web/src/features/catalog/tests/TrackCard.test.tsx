import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import TrackCard from '../components/TrackCard';
import type { Track } from '../types';

const baseTrack: Track = {
  id: 10,
  name: 'Schism',
  album: 'http://localhost/api/v1/albums/5/',
  duration_ms: 412000,
  track_number: 3,
  explicit: false,
  spotify_id: 'track-123',
};

describe('TrackCard', () => {
  it('renders a fallback glyph when artwork is missing', () => {
    render(<TrackCard track={baseTrack} />);

    expect(screen.getByLabelText('Schism artwork')).toBeInTheDocument();
  });

  it('renders artwork when a URL is provided', () => {
    render(<TrackCard track={baseTrack} artworkUrl="https://example.com/art.jpg" />);

    expect(screen.getByAltText('Schism artwork')).toHaveAttribute('src', 'https://example.com/art.jpg');
  });

  it('calls onPlay when interactive', () => {
    const handlePlay = vi.fn();
    render(<TrackCard track={baseTrack} onPlay={handlePlay} />);

    fireEvent.click(screen.getByRole('button', { name: /play schism/i }));

    expect(handlePlay).toHaveBeenCalledWith(baseTrack);
  });
});
