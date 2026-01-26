/**
 * VISUALIZATION OPTION A: Card Stack Wizard
 *
 * Design Philosophy:
 * - Full-screen immersive cards that slide horizontally
 * - One question per screen for focused attention
 * - Smooth animations between steps
 * - Large touch targets for mobile
 * - Progress bar at top
 *
 * Best for: Mobile-first, focused experiences
 */

import { useState } from 'react';
import './visualizations.css';

// Mock data for demonstration
const MOCK_GENRES = [
  { id: '1', name: 'Hip-Hop', artists: ['Drake', 'Kendrick Lamar', 'J. Cole'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b273cd945b4e3de57edd28481a3f' },
  { id: '2', name: 'Rock', artists: ['Foo Fighters', 'Green Day', 'Nirvana'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b273e8b066f70c206551210d902b' },
  { id: '3', name: 'Pop', artists: ['Taylor Swift', 'Dua Lipa', 'The Weeknd'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b273c6b577e4c4a6d326354a89f7' },
  { id: '4', name: 'R&B', artists: ['SZA', 'Frank Ocean', 'Daniel Caesar'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b2730c471c36970b9406233842a5' },
  { id: '5', name: 'Electronic', artists: ['Daft Punk', 'Calvin Harris', 'Disclosure'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b273b33d46dfa2f8e1e5e9d33e14' },
  { id: '6', name: 'Country', artists: ['Morgan Wallen', 'Luke Combs', 'Chris Stapleton'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b273d0ec2db5b1c5b0a0c5d88f27' },
  { id: '7', name: 'Jazz', artists: ['Kamasi Washington', 'Robert Glasper', 'Esperanza Spalding'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b2731a5b6271ae1c8497df20916e' },
  { id: '8', name: 'Classical', artists: ['Yo-Yo Ma', 'Lang Lang', 'Hilary Hahn'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b2739a1c5a6e26e20f093d8671e2' },
  { id: '9', name: 'Latin', artists: ['Bad Bunny', 'J Balvin', 'Rosalía'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b2733c7c0f1e5a7d2a8b9f5b9a7c' },
  { id: '10', name: 'Indie', artists: ['Tame Impala', 'Arctic Monkeys', 'Mac DeMarco'], imageUrl: 'https://i.scdn.co/image/ab67616d0000b2738b52c6b9bc4e43d873869699' },
];

const DECADES = ['60s', '70s', '80s', '90s', '2000s', '2010s', '2020s'];
const AGE_RANGES = ['18-24', '25-34', '35-44', '45-54', '55+'];

type Step = 'genres' | 'artist' | 'hated' | 'rainy' | 'workout' | 'decade' | 'listening' | 'age' | 'location' | 'complete';

export default function OptionA_CardStack() {
  const [currentStep, setCurrentStep] = useState<Step>('genres');
  const [direction, setDirection] = useState<'forward' | 'backward'>('forward');
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [selectedDecade, setSelectedDecade] = useState<string | null>(null);
  const [listeningStyle, setListeningStyle] = useState<'playlist' | 'album' | null>(null);
  const [ageRange, setAgeRange] = useState<string | null>(null);

  const steps: Step[] = ['genres', 'artist', 'hated', 'rainy', 'workout', 'decade', 'listening', 'age', 'location', 'complete'];
  const currentIndex = steps.indexOf(currentStep);
  const progress = ((currentIndex) / (steps.length - 1)) * 100;

  const goNext = () => {
    if (currentIndex < steps.length - 1) {
      setDirection('forward');
      setCurrentStep(steps[currentIndex + 1]);
    }
  };

  const goBack = () => {
    if (currentIndex > 0) {
      setDirection('backward');
      setCurrentStep(steps[currentIndex - 1]);
    }
  };

  const toggleGenre = (genreId: string) => {
    setSelectedGenres(prev => {
      if (prev.includes(genreId)) {
        return prev.filter(id => id !== genreId);
      }
      if (prev.length >= 3) return prev;
      return [...prev, genreId];
    });
  };

  return (
    <div className="viz-container viz-card-stack">
      {/* Progress Bar */}
      <div className="viz-progress-bar">
        <div className="viz-progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Back Button */}
      {currentIndex > 0 && currentStep !== 'complete' && (
        <button className="viz-back-btn" onClick={goBack}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Card Container */}
      <div className={`viz-card-container ${direction}`}>

        {/* Step 1: Genres */}
        {currentStep === 'genres' && (
          <div className="viz-card viz-card-enter">
            <div className="viz-card-content">
              <span className="viz-step-label">Step 1 of 9</span>
              <h1 className="viz-title">What are your top 3 genres?</h1>
              <p className="viz-subtitle">These help us understand your musical identity</p>

              <div className="viz-genre-grid">
                {MOCK_GENRES.map(genre => (
                  <button
                    key={genre.id}
                    className={`viz-genre-card ${selectedGenres.includes(genre.id) ? 'selected' : ''}`}
                    onClick={() => toggleGenre(genre.id)}
                    disabled={selectedGenres.length >= 3 && !selectedGenres.includes(genre.id)}
                  >
                    <div className="viz-genre-images">
                      {[1, 2, 3].map(i => (
                        <div key={i} className="viz-genre-image-placeholder" />
                      ))}
                    </div>
                    <span className="viz-genre-name">{genre.name}</span>
                    <span className="viz-genre-artists">{genre.artists.join(', ')}</span>
                    {selectedGenres.includes(genre.id) && (
                      <div className="viz-genre-check">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </div>
                    )}
                  </button>
                ))}
              </div>

              <div className="viz-selection-count">
                {selectedGenres.length}/3 selected
              </div>
            </div>

            <button
              className="viz-next-btn"
              onClick={goNext}
              disabled={selectedGenres.length === 0}
            >
              Continue
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        )}

        {/* Step 2: Ride or Die Artist */}
        {currentStep === 'artist' && (
          <div className="viz-card viz-card-enter">
            <div className="viz-card-content">
              <span className="viz-step-label">Step 2 of 9</span>
              <h1 className="viz-title">Your ride-or-die artist?</h1>
              <p className="viz-subtitle">That one artist you&apos;ll defend to the end</p>

              <div className="viz-search-container">
                <svg className="viz-search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" />
                  <path d="M21 21l-4.35-4.35" />
                </svg>
                <input
                  type="text"
                  className="viz-search-input"
                  placeholder="Search for an artist..."
                />
              </div>

              <div className="viz-artist-suggestions">
                <p className="viz-suggestions-label">Popular choices:</p>
                <div className="viz-artist-chips">
                  {['Beyoncé', 'Radiohead', 'Kanye West', 'Taylor Swift', 'Kendrick Lamar'].map(artist => (
                    <button key={artist} className="viz-artist-chip">
                      <div className="viz-artist-chip-avatar" />
                      {artist}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="viz-btn-row">
              <button className="viz-skip-btn" onClick={goNext}>
                Skip for now
              </button>
              <button className="viz-next-btn" onClick={goNext}>
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Step 6: Decade */}
        {currentStep === 'decade' && (
          <div className="viz-card viz-card-enter">
            <div className="viz-card-content">
              <span className="viz-step-label">Step 6 of 9</span>
              <h1 className="viz-title">What decade speaks to you?</h1>
              <p className="viz-subtitle">The era that shaped your taste</p>

              <div className="viz-decade-grid">
                {DECADES.map(decade => (
                  <button
                    key={decade}
                    className={`viz-decade-btn ${selectedDecade === decade ? 'selected' : ''}`}
                    onClick={() => setSelectedDecade(decade)}
                  >
                    <span className="viz-decade-label">{decade}</span>
                    <span className="viz-decade-vibe">
                      {decade === '60s' && 'Psychedelic & Soul'}
                      {decade === '70s' && 'Disco & Punk'}
                      {decade === '80s' && 'Synth & New Wave'}
                      {decade === '90s' && 'Grunge & Hip-Hop'}
                      {decade === '2000s' && 'Pop Punk & R&B'}
                      {decade === '2010s' && 'EDM & Streaming'}
                      {decade === '2020s' && 'Hyperpop & Revival'}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <button className="viz-next-btn" onClick={goNext}>
              Continue
            </button>
          </div>
        )}

        {/* Step 7: Playlist vs Album */}
        {currentStep === 'listening' && (
          <div className="viz-card viz-card-enter">
            <div className="viz-card-content">
              <span className="viz-step-label">Step 7 of 9</span>
              <h1 className="viz-title">How do you listen?</h1>
              <p className="viz-subtitle">Everyone has their style</p>

              <div className="viz-binary-choice">
                <button
                  className={`viz-choice-card ${listeningStyle === 'playlist' ? 'selected' : ''}`}
                  onClick={() => setListeningStyle('playlist')}
                >
                  <div className="viz-choice-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M21 15V6a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2h8" />
                      <path d="M16 2v4M8 2v4M3 10h18" />
                      <path d="M16 19h6M19 16v6" />
                    </svg>
                  </div>
                  <h3>Playlist Person</h3>
                  <p>Curated vibes, shuffle on, discover new tracks mixed with favorites</p>
                </button>

                <button
                  className={`viz-choice-card ${listeningStyle === 'album' ? 'selected' : ''}`}
                  onClick={() => setListeningStyle('album')}
                >
                  <div className="viz-choice-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <circle cx="12" cy="12" r="10" />
                      <circle cx="12" cy="12" r="3" />
                      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
                    </svg>
                  </div>
                  <h3>Album Listener</h3>
                  <p>Front to back, artist&apos;s vision, the way it was meant to be heard</p>
                </button>
              </div>
            </div>

            <button
              className="viz-next-btn"
              onClick={goNext}
              disabled={!listeningStyle}
            >
              Continue
            </button>
          </div>
        )}

        {/* Step 8: Age */}
        {currentStep === 'age' && (
          <div className="viz-card viz-card-enter">
            <div className="viz-card-content">
              <span className="viz-step-label">Step 8 of 9</span>
              <h1 className="viz-title">What&apos;s your age range?</h1>
              <p className="viz-subtitle">Helps us personalize your experience</p>

              <div className="viz-pill-row">
                {AGE_RANGES.map(range => (
                  <button
                    key={range}
                    className={`viz-pill ${ageRange === range ? 'selected' : ''}`}
                    onClick={() => setAgeRange(range)}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>

            <button
              className="viz-next-btn"
              onClick={goNext}
              disabled={!ageRange}
            >
              Continue
            </button>
          </div>
        )}

        {/* Placeholder for other steps */}
        {['hated', 'rainy', 'workout', 'location'].includes(currentStep) && (
          <div className="viz-card viz-card-enter">
            <div className="viz-card-content">
              <span className="viz-step-label">Step {currentIndex + 1} of 9</span>
              <h1 className="viz-title">
                {currentStep === 'hated' && "Any genres you can&apos;t stand?"}
                {currentStep === 'rainy' && "What&apos;s your rainy day soundtrack?"}
                {currentStep === 'workout' && "What powers your workout?"}
                {currentStep === 'location' && "Where are you located?"}
              </h1>
              <p className="viz-subtitle">
                {currentStep === 'hated' && "We&apos;ll make sure to avoid these"}
                {currentStep === 'rainy' && "When the mood is mellow"}
                {currentStep === 'workout' && "Your energy anthem"}
                {currentStep === 'location' && "We&apos;ll place you on the Juke World map"}
              </p>

              <div className="viz-placeholder">
                [Interactive content for {currentStep}]
              </div>
            </div>

            <button className="viz-next-btn" onClick={goNext}>
              Continue
            </button>
          </div>
        )}

        {/* Complete */}
        {currentStep === 'complete' && (
          <div className="viz-card viz-card-enter viz-complete-card">
            <div className="viz-card-content">
              <div className="viz-complete-icon">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <h1 className="viz-title">You&apos;re all set!</h1>
              <p className="viz-subtitle">Your music identity has been created</p>

              <div className="viz-summary">
                <div className="viz-summary-item">
                  <span className="viz-summary-label">Genres</span>
                  <span className="viz-summary-value">{selectedGenres.length} selected</span>
                </div>
                <div className="viz-summary-item">
                  <span className="viz-summary-label">Decade</span>
                  <span className="viz-summary-value">{selectedDecade || 'Not set'}</span>
                </div>
                <div className="viz-summary-item">
                  <span className="viz-summary-label">Style</span>
                  <span className="viz-summary-value">{listeningStyle || 'Not set'}</span>
                </div>
              </div>
            </div>

            <button className="viz-next-btn viz-final-btn">
              Connect Spotify & Enter Juke World
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polygon points="10 8 16 12 10 16 10 8" />
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Design Label */}
      <div className="viz-design-label">
        Option A: Card Stack Wizard
      </div>
    </div>
  );
}
