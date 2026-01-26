/**
 * VISUALIZATION OPTION B: Chat-Style Wizard
 *
 * Design Philosophy:
 * - Conversational interface like messaging apps
 * - Questions appear as "Juke" messages
 * - User responses appear on the other side
 * - Typing indicators for personality
 * - Scrolling conversation history
 *
 * Best for: Engaging, personality-driven, younger audience
 */

import { useState, useEffect, useRef } from 'react';
import './visualizations.css';

type Message = {
  id: string;
  type: 'juke' | 'user';
  content: string;
  component?: 'genres' | 'artist' | 'decade' | 'listening' | 'pills';
  options?: string[];
  timestamp: Date;
};

const GENRES = ['Hip-Hop', 'Rock', 'Pop', 'R&B', 'Electronic', 'Country', 'Jazz', 'Classical', 'Latin', 'Indie'];
const DECADES = ['60s', '70s', '80s', '90s', '2000s', '2010s', '2020s'];
const QUESTIONS = [
  { text: "Hey! Welcome to Juke! 🎵 I'm so excited to help you build your music identity.", delay: 1000 },
  { text: "Let's start with the big one... What are your top 3 genres?", component: 'genres' as const, delay: 1500 },
  { text: "Great taste! Now, is there one artist you'll absolutely ride or die for?", component: 'artist' as const, delay: 1200 },
  { text: 'What decade of music speaks to your soul?', component: 'decade' as const, delay: 1000 },
  {
    text: 'Last one - are you a playlist shuffler or an album-front-to-back kind of person?',
    component: 'listening' as const,
    delay: 1200,
  },
  { text: 'Amazing! Your music identity is looking incredible. Ready to join Juke World? 🌍', delay: 1000 },
];

export default function OptionB_ChatStyle() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentQuestion < QUESTIONS.length) {
      const typingTimer = setTimeout(() => setIsTyping(true), 0);
      const timer = setTimeout(() => {
        setIsTyping(false);
        const q = QUESTIONS[currentQuestion];
        setMessages(prev => [...prev, {
          id: `juke-${currentQuestion}`,
          type: 'juke',
          content: q.text,
          component: q.component,
          timestamp: new Date(),
        }]);
      }, QUESTIONS[currentQuestion].delay);
      return () => {
        clearTimeout(typingTimer);
        clearTimeout(timer);
      };
    }
  }, [currentQuestion]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleUserResponse = (response: string, nextQuestion = true) => {
    setMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      type: 'user',
      content: response,
      timestamp: new Date(),
    }]);
    if (nextQuestion) {
      setTimeout(() => setCurrentQuestion(prev => prev + 1), 500);
    }
  };

  const toggleGenre = (genre: string) => {
    setSelectedGenres(prev => {
      if (prev.includes(genre)) return prev.filter(g => g !== genre);
      if (prev.length >= 3) return prev;
      return [...prev, genre];
    });
  };

  const submitGenres = () => {
    if (selectedGenres.length > 0) {
      handleUserResponse(selectedGenres.join(', '));
    }
  };

  return (
    <div className="viz-container viz-chat">
      {/* Chat Header */}
      <div className="viz-chat-header">
        <div className="viz-chat-avatar">
          <span>J</span>
        </div>
        <div className="viz-chat-info">
          <h2>Juke</h2>
          <span className="viz-chat-status">
            {isTyping ? 'typing...' : 'online'}
          </span>
        </div>
      </div>

      {/* Messages Container */}
      <div className="viz-chat-messages">
        {messages.map(msg => (
          <div key={msg.id} className={`viz-message viz-message-${msg.type}`}>
            {msg.type === 'juke' && (
              <div className="viz-message-avatar">J</div>
            )}
            <div className="viz-message-bubble">
              <p>{msg.content}</p>

              {/* Genre Selection */}
              {msg.component === 'genres' && currentQuestion === 1 && (
                <div className="viz-chat-genres">
                  <div className="viz-chat-genre-grid">
                    {GENRES.map(genre => (
                      <button
                        key={genre}
                        className={`viz-chat-genre-btn ${selectedGenres.includes(genre) ? 'selected' : ''}`}
                        onClick={() => toggleGenre(genre)}
                        disabled={selectedGenres.length >= 3 && !selectedGenres.includes(genre)}
                      >
                        {genre}
                        {selectedGenres.includes(genre) && ' ✓'}
                      </button>
                    ))}
                  </div>
                  <button
                    className="viz-chat-send-btn"
                    onClick={submitGenres}
                    disabled={selectedGenres.length === 0}
                  >
                    Send ({selectedGenres.length}/3)
                  </button>
                </div>
              )}

              {/* Artist Search */}
              {msg.component === 'artist' && currentQuestion === 2 && (
                <div className="viz-chat-input-area">
                  <input
                    type="text"
                    placeholder="Search for an artist..."
                    className="viz-chat-text-input"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.target as HTMLInputElement).value) {
                        handleUserResponse((e.target as HTMLInputElement).value);
                      }
                    }}
                  />
                  <button
                    className="viz-chat-skip"
                    onClick={() => handleUserResponse("I can't pick just one!")}
                  >
                    Skip
                  </button>
                </div>
              )}

              {/* Decade Selection */}
              {msg.component === 'decade' && currentQuestion === 3 && (
                <div className="viz-chat-decades">
                  {DECADES.map(decade => (
                    <button
                      key={decade}
                      className="viz-chat-decade-btn"
                      onClick={() => handleUserResponse(decade)}
                    >
                      {decade}
                    </button>
                  ))}
                </div>
              )}

              {/* Listening Style */}
              {msg.component === 'listening' && currentQuestion === 4 && (
                <div className="viz-chat-binary">
                  <button
                    className="viz-chat-choice-btn"
                    onClick={() => handleUserResponse("Playlist shuffler 🔀")}
                  >
                    <span className="viz-choice-emoji">🔀</span>
                    Playlist Shuffler
                  </button>
                  <button
                    className="viz-chat-choice-btn"
                    onClick={() => handleUserResponse("Album listener 💿")}
                  >
                    <span className="viz-choice-emoji">💿</span>
                    Album Listener
                  </button>
                </div>
              )}
            </div>
            <span className="viz-message-time">
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}

        {/* Typing Indicator */}
        {isTyping && (
          <div className="viz-message viz-message-juke">
            <div className="viz-message-avatar">J</div>
            <div className="viz-typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        {/* Final CTA */}
        {currentQuestion >= QUESTIONS.length && (
          <div className="viz-chat-final">
            <button className="viz-chat-final-btn">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
              </svg>
              Connect Spotify & Enter Juke World
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Design Label */}
      <div className="viz-design-label">
        Option B: Chat-Style Wizard
      </div>
    </div>
  );
}
