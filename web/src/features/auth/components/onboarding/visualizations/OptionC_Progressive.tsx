/**
 * VISUALIZATION OPTION C: Progressive Single-Page Wizard
 *
 * Design Philosophy:
 * - Single scrollable page with sections
 * - Sticky progress indicator on the side
 * - Sections unlock/reveal as you complete previous ones
 * - Visible overview of entire journey
 * - Smooth scroll animations between sections
 *
 * Best for: Desktop-first, users who like to see full scope, less "trapped" feeling
 */

import { useState, useRef } from 'react';
import './visualizations.css';

const GENRES = [
  { id: 'hiphop', name: 'Hip-Hop', artists: ['Drake', 'Kendrick', 'J. Cole'] },
  { id: 'rock', name: 'Rock', artists: ['Foo Fighters', 'Green Day', 'Nirvana'] },
  { id: 'pop', name: 'Pop', artists: ['Taylor Swift', 'Dua Lipa', 'The Weeknd'] },
  { id: 'rnb', name: 'R&B', artists: ['SZA', 'Frank Ocean', 'Daniel Caesar'] },
  { id: 'electronic', name: 'Electronic', artists: ['Daft Punk', 'Calvin Harris', 'Disclosure'] },
  { id: 'country', name: 'Country', artists: ['Morgan Wallen', 'Luke Combs', 'Chris Stapleton'] },
  { id: 'jazz', name: 'Jazz', artists: ['Kamasi Washington', 'Robert Glasper', 'Esperanza'] },
  { id: 'classical', name: 'Classical', artists: ['Yo-Yo Ma', 'Lang Lang', 'Hilary Hahn'] },
  { id: 'latin', name: 'Latin', artists: ['Bad Bunny', 'J Balvin', 'Rosalía'] },
  { id: 'indie', name: 'Indie', artists: ['Tame Impala', 'Arctic Monkeys', 'Mac DeMarco'] },
];

const DECADES = [
  { id: '60s', label: '60s', vibe: 'Psychedelic & Soul' },
  { id: '70s', label: '70s', vibe: 'Disco & Punk' },
  { id: '80s', label: '80s', vibe: 'Synth & New Wave' },
  { id: '90s', label: '90s', vibe: 'Grunge & Golden Era Hip-Hop' },
  { id: '2000s', label: '2000s', vibe: 'Pop Punk & Crunk' },
  { id: '2010s', label: '2010s', vibe: 'EDM & Streaming Era' },
  { id: '2020s', label: '2020s', vibe: 'Hyperpop & TikTok' },
];

const MOODS = [
  { id: 'mellow', label: 'Mellow & Acoustic', icon: '🌧️' },
  { id: 'jazz', label: 'Jazz & Lo-fi', icon: '☕' },
  { id: 'indie', label: 'Indie & Chill', icon: '🌿' },
  { id: 'classical', label: 'Classical & Ambient', icon: '🎻' },
  { id: 'rnb', label: 'R&B & Soul', icon: '💜' },
];

const WORKOUT_VIBES = [
  { id: 'intense', label: 'Maximum Intensity', icon: '🔥', desc: 'Heavy bass, fast tempo' },
  { id: 'hiphop', label: 'Hip-Hop Energy', icon: '💪', desc: 'Beats that hit hard' },
  { id: 'rock', label: 'Rock Power', icon: '🎸', desc: 'Guitar-driven adrenaline' },
  { id: 'edm', label: 'EDM Drops', icon: '⚡', desc: 'Build-ups and releases' },
  { id: 'pop', label: 'Pop Anthems', icon: '🎤', desc: 'Sing-along motivation' },
];

type Section = 'genres' | 'artist' | 'preferences' | 'about' | 'complete';

export default function OptionC_Progressive() {
  const [completedSections, setCompletedSections] = useState<Section[]>([]);
  const [activeSection, setActiveSection] = useState<Section>('genres');
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [selectedDecade, setSelectedDecade] = useState<string | null>(null);
  const [rainyMood, setRainyMood] = useState<string | null>(null);
  const [workoutVibe, setWorkoutVibe] = useState<string | null>(null);
  const [listeningStyle, setListeningStyle] = useState<'playlist' | 'album' | null>(null);

  const genresRef = useRef<HTMLDivElement>(null);
  const artistRef = useRef<HTMLDivElement>(null);
  const preferencesRef = useRef<HTMLDivElement>(null);
  const aboutRef = useRef<HTMLDivElement>(null);
  const completeRef = useRef<HTMLDivElement>(null);

  const sections: { id: Section; label: string; number: number }[] = [
    { id: 'genres', label: 'Your Genres', number: 1 },
    { id: 'artist', label: 'Ride or Die', number: 2 },
    { id: 'preferences', label: 'Your Vibes', number: 3 },
    { id: 'about', label: 'About You', number: 4 },
    { id: 'complete', label: 'Welcome', number: 5 },
  ];

  const getSectionRef = (section: Section) => {
    switch (section) {
      case 'genres':
        return genresRef;
      case 'artist':
        return artistRef;
      case 'preferences':
        return preferencesRef;
      case 'about':
        return aboutRef;
      case 'complete':
        return completeRef;
      default:
        return genresRef;
    }
  };

  const toggleGenre = (genreId: string) => {
    setSelectedGenres(prev => {
      if (prev.includes(genreId)) return prev.filter(id => id !== genreId);
      if (prev.length >= 3) return prev;
      return [...prev, genreId];
    });
  };

  const completeSection = (section: Section) => {
    if (!completedSections.includes(section)) {
      setCompletedSections(prev => [...prev, section]);
    }
    const currentIndex = sections.findIndex(s => s.id === section);
    if (currentIndex < sections.length - 1) {
      const nextSection = sections[currentIndex + 1].id;
      setActiveSection(nextSection);
      getSectionRef(nextSection).current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  const isSectionUnlocked = (section: Section) => {
    const index = sections.findIndex(s => s.id === section);
    if (index === 0) return true;
    const prevSection = sections[index - 1].id;
    return completedSections.includes(prevSection);
  };

  const scrollToSection = (section: Section) => {
    if (isSectionUnlocked(section)) {
      setActiveSection(section);
      getSectionRef(section).current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  return (
    <div className="viz-container viz-progressive">
      {/* Sticky Side Progress */}
      <div className="viz-prog-sidebar">
        <div className="viz-prog-logo">
          <span>JUKE</span>
        </div>
        <nav className="viz-prog-nav">
          {sections.map(section => (
            <button
              key={section.id}
              className={`viz-prog-nav-item ${activeSection === section.id ? 'active' : ''} ${completedSections.includes(section.id) ? 'completed' : ''} ${!isSectionUnlocked(section.id) ? 'locked' : ''}`}
              onClick={() => scrollToSection(section.id)}
              disabled={!isSectionUnlocked(section.id)}
            >
              <span className="viz-prog-nav-number">
                {completedSections.includes(section.id) ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  section.number
                )}
              </span>
              <span className="viz-prog-nav-label">{section.label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content */}
      <div className="viz-prog-content">
        {/* Section 1: Genres */}
        <section
          ref={genresRef}
          className={`viz-prog-section ${activeSection === 'genres' ? 'active' : ''} ${completedSections.includes('genres') ? 'completed' : ''}`}
        >
          <div className="viz-prog-section-header">
            <span className="viz-prog-section-number">01</span>
            <h2>What are your top 3 genres?</h2>
            <p>Pick the sounds that define you</p>
          </div>

          <div className="viz-prog-genre-grid">
            {GENRES.map(genre => (
              <button
                key={genre.id}
                className={`viz-prog-genre-card ${selectedGenres.includes(genre.id) ? 'selected' : ''}`}
                onClick={() => toggleGenre(genre.id)}
                disabled={selectedGenres.length >= 3 && !selectedGenres.includes(genre.id)}
              >
                <div className="viz-prog-genre-art">
                  <div className="viz-prog-genre-art-grid">
                    <div /><div /><div />
                  </div>
                </div>
                <div className="viz-prog-genre-info">
                  <h3>{genre.name}</h3>
                  <p>{genre.artists.join(' • ')}</p>
                </div>
                {selectedGenres.includes(genre.id) && (
                  <div className="viz-prog-genre-check">✓</div>
                )}
              </button>
            ))}
          </div>

          <div className="viz-prog-section-footer">
            <span className="viz-prog-selection-count">{selectedGenres.length}/3 selected</span>
            <button
              className="viz-prog-continue-btn"
              onClick={() => completeSection('genres')}
              disabled={selectedGenres.length === 0}
            >
              Continue
            </button>
          </div>
        </section>

        {/* Section 2: Artist */}
        <section
          ref={artistRef}
          className={`viz-prog-section ${activeSection === 'artist' ? 'active' : ''} ${!isSectionUnlocked('artist') ? 'locked' : ''}`}
        >
          <div className="viz-prog-section-header">
            <span className="viz-prog-section-number">02</span>
            <h2>Your ride-or-die artist?</h2>
            <p>The one you&apos;ll defend to the end</p>
          </div>

          {isSectionUnlocked('artist') && (
            <>
              <div className="viz-prog-search-area">
                <div className="viz-prog-search-box">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" />
                    <path d="M21 21l-4.35-4.35" />
                  </svg>
                  <input type="text" placeholder="Search for an artist..." />
                </div>
              </div>

              <div className="viz-prog-section-footer">
                <button className="viz-prog-skip-btn" onClick={() => completeSection('artist')}>
                  Skip this one
                </button>
                <button className="viz-prog-continue-btn" onClick={() => completeSection('artist')}>
                  Continue
                </button>
              </div>
            </>
          )}
        </section>

        {/* Section 3: Preferences */}
        <section
          ref={preferencesRef}
          className={`viz-prog-section ${activeSection === 'preferences' ? 'active' : ''} ${!isSectionUnlocked('preferences') ? 'locked' : ''}`}
        >
          <div className="viz-prog-section-header">
            <span className="viz-prog-section-number">03</span>
            <h2>Tell us about your vibes</h2>
            <p>How do you like to experience music?</p>
          </div>

          {isSectionUnlocked('preferences') && (
            <>
              {/* Rainy Day */}
              <div className="viz-prog-subsection">
                <h3>What&apos;s your rainy day soundtrack?</h3>
                <div className="viz-prog-mood-grid">
                  {MOODS.map(mood => (
                    <button
                      key={mood.id}
                      className={`viz-prog-mood-card ${rainyMood === mood.id ? 'selected' : ''}`}
                      onClick={() => setRainyMood(mood.id)}
                    >
                      <span className="viz-prog-mood-icon">{mood.icon}</span>
                      <span className="viz-prog-mood-label">{mood.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Workout */}
              <div className="viz-prog-subsection">
                <h3>What powers your workout?</h3>
                <div className="viz-prog-workout-grid">
                  {WORKOUT_VIBES.map(vibe => (
                    <button
                      key={vibe.id}
                      className={`viz-prog-workout-card ${workoutVibe === vibe.id ? 'selected' : ''}`}
                      onClick={() => setWorkoutVibe(vibe.id)}
                    >
                      <span className="viz-prog-workout-icon">{vibe.icon}</span>
                      <div className="viz-prog-workout-info">
                        <span className="viz-prog-workout-label">{vibe.label}</span>
                        <span className="viz-prog-workout-desc">{vibe.desc}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Listening Style */}
              <div className="viz-prog-subsection">
                <h3>How do you listen?</h3>
                <div className="viz-prog-binary-row">
                  <button
                    className={`viz-prog-binary-card ${listeningStyle === 'playlist' ? 'selected' : ''}`}
                    onClick={() => setListeningStyle('playlist')}
                  >
                    <span className="viz-prog-binary-icon">🔀</span>
                    <span className="viz-prog-binary-label">Playlist Person</span>
                    <span className="viz-prog-binary-desc">Shuffle & discover</span>
                  </button>
                  <button
                    className={`viz-prog-binary-card ${listeningStyle === 'album' ? 'selected' : ''}`}
                    onClick={() => setListeningStyle('album')}
                  >
                    <span className="viz-prog-binary-icon">💿</span>
                    <span className="viz-prog-binary-label">Album Listener</span>
                    <span className="viz-prog-binary-desc">Front to back</span>
                  </button>
                </div>
              </div>

              <div className="viz-prog-section-footer">
                <button className="viz-prog-continue-btn" onClick={() => completeSection('preferences')}>
                  Continue
                </button>
              </div>
            </>
          )}
        </section>

        {/* Section 4: About You */}
        <section
          ref={aboutRef}
          className={`viz-prog-section ${activeSection === 'about' ? 'active' : ''} ${!isSectionUnlocked('about') ? 'locked' : ''}`}
        >
          <div className="viz-prog-section-header">
            <span className="viz-prog-section-number">04</span>
            <h2>A bit about you</h2>
            <p>Help us place you on the map</p>
          </div>

          {isSectionUnlocked('about') && (
            <>
              {/* Decade */}
              <div className="viz-prog-subsection">
                <h3>What decade speaks to you?</h3>
                <div className="viz-prog-decade-row">
                  {DECADES.map(decade => (
                    <button
                      key={decade.id}
                      className={`viz-prog-decade-btn ${selectedDecade === decade.id ? 'selected' : ''}`}
                      onClick={() => setSelectedDecade(decade.id)}
                    >
                      <span className="viz-prog-decade-label">{decade.label}</span>
                      <span className="viz-prog-decade-vibe">{decade.vibe}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Location */}
              <div className="viz-prog-subsection">
                <h3>Where are you located?</h3>
                <div className="viz-prog-search-box">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                    <circle cx="12" cy="10" r="3" />
                  </svg>
                  <input type="text" placeholder="Search for your city..." />
                </div>
                <p className="viz-prog-location-note">We&apos;ll place you on the Juke World globe!</p>
              </div>

              <div className="viz-prog-section-footer">
                <button className="viz-prog-continue-btn" onClick={() => completeSection('about')}>
                  Continue
                </button>
              </div>
            </>
          )}
        </section>

        {/* Section 5: Complete */}
        <section
          ref={completeRef}
          className={`viz-prog-section viz-prog-complete ${activeSection === 'complete' ? 'active' : ''} ${!isSectionUnlocked('complete') ? 'locked' : ''}`}
        >
          {isSectionUnlocked('complete') && (
            <div className="viz-prog-complete-content">
              <div className="viz-prog-complete-icon">
                <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 2a10 10 0 00-7.07 17.07" strokeDasharray="4 4" />
                  <polygon points="10 8 16 12 10 16 10 8" fill="currentColor" />
                </svg>
              </div>
              <h2>Your music identity is ready!</h2>
              <p>Connect Spotify to complete your profile and join Juke World</p>

              <div className="viz-prog-summary-grid">
                <div className="viz-prog-summary-card">
                  <span className="viz-prog-summary-label">Genres</span>
                  <span className="viz-prog-summary-value">{selectedGenres.length} selected</span>
                </div>
                <div className="viz-prog-summary-card">
                  <span className="viz-prog-summary-label">Era</span>
                  <span className="viz-prog-summary-value">{selectedDecade || '—'}</span>
                </div>
                <div className="viz-prog-summary-card">
                  <span className="viz-prog-summary-label">Style</span>
                  <span className="viz-prog-summary-value">{listeningStyle || '—'}</span>
                </div>
              </div>

              <button className="viz-prog-final-btn">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
                </svg>
                Connect Spotify & Enter Juke World
              </button>
            </div>
          )}
        </section>
      </div>

      {/* Design Label */}
      <div className="viz-design-label">
        Option C: Progressive Single-Page
      </div>
    </div>
  );
}
