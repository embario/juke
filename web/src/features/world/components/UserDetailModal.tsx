import { MusicProfile } from '../../profiles/types';
import { getGenreColor } from '../constants';

type Props = {
  user: MusicProfile | null;
  loading: boolean;
  clout: number;
  topGenre: string;
  onClose: () => void;
};

export default function UserDetailModal({ user, loading, clout, topGenre, onClose }: Props) {
  if (!user && !loading) return null;

  const genreColor = getGenreColor(topGenre);

  return (
    <div
      style={{
        position: 'absolute',
        top: 80,
        right: 24,
        width: 300,
        background: 'rgba(10,10,20,0.92)',
        backdropFilter: 'blur(16px)',
        borderRadius: 12,
        border: '1px solid rgba(255,255,255,0.1)',
        padding: 20,
        zIndex: 20,
        fontFamily: 'system-ui, -apple-system, sans-serif',
        color: '#fff',
      }}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: '20px 0', color: 'rgba(255,255,255,0.5)' }}>
          Loading profile...
        </div>
      ) : user ? (
        <>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              {user.avatar_url && (
                <img
                  src={user.avatar_url}
                  alt=""
                  style={{ width: 40, height: 40, borderRadius: '50%', objectFit: 'cover' }}
                />
              )}
              <div>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{user.display_name || user.username}</div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2 }}>
                  @{user.username}
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'rgba(255,255,255,0.1)',
                border: 'none',
                borderRadius: 6,
                color: '#fff',
                width: 28,
                height: 28,
                cursor: 'pointer',
                fontSize: 16,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              &times;
            </button>
          </div>

          {/* Tagline */}
          {user.tagline && (
            <div style={{ marginTop: 12, fontSize: 13, color: 'rgba(255,255,255,0.6)', fontStyle: 'italic' }}>
              {user.tagline}
            </div>
          )}

          {/* Clout meter */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 6, letterSpacing: '0.5px' }}>
              CLOUT
            </div>
            <div
              style={{
                height: 8,
                background: 'rgba(255,255,255,0.1)',
                borderRadius: 4,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${clout * 100}%`,
                  height: '100%',
                  background: genreColor,
                  borderRadius: 4,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>
              {Math.round(clout * 100)}
              <span style={{ fontSize: 12, fontWeight: 400, color: 'rgba(255,255,255,0.5)' }}> /100</span>
            </div>
          </div>

          {/* Genre chips */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 8, letterSpacing: '0.5px' }}>
              TOP GENRES
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {user.favorite_genres.slice(0, 5).map((genre) => (
                <span
                  key={genre}
                  style={{
                    display: 'inline-block',
                    padding: '4px 10px',
                    borderRadius: 20,
                    background: `${getGenreColor(genre)}22`,
                    color: getGenreColor(genre),
                    fontSize: 12,
                    fontWeight: 500,
                    textTransform: 'capitalize',
                  }}
                >
                  {genre}
                </span>
              ))}
            </div>
          </div>

          {/* Favorite artists */}
          {user.favorite_artists.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 6, letterSpacing: '0.5px' }}>
                FAVORITE ARTISTS
              </div>
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)', lineHeight: 1.5 }}>
                {user.favorite_artists.slice(0, 4).join(', ')}
                {user.favorite_artists.length > 4 && (
                  <span style={{ color: 'rgba(255,255,255,0.4)' }}>
                    {' '}+{user.favorite_artists.length - 4} more
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Location */}
          {user.location && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 4, letterSpacing: '0.5px' }}>
                LOCATION
              </div>
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>{user.location}</div>
            </div>
          )}

          {/* View profile link */}
          <a
            href={`/profiles/${user.username}`}
            style={{
              display: 'block',
              marginTop: 20,
              padding: '10px 0',
              textAlign: 'center',
              background: 'rgba(255,255,255,0.1)',
              borderRadius: 8,
              color: '#fff',
              textDecoration: 'none',
              fontSize: 13,
              fontWeight: 500,
              transition: 'background 0.2s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.2)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.1)')}
          >
            View Full Profile &rarr;
          </a>
        </>
      ) : null}
    </div>
  );
}
