import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import JukeGlobe from '../components/JukeGlobe';
import GlobeOverlayNav from '../components/GlobeOverlayNav';
import UserDetailModal from '../components/UserDetailModal';
import { useGlobePoints } from '../hooks/useGlobePoints';
import { useUserDetail } from '../hooks/useUserDetail';
import { GlobePoint } from '../types';
import { useAuth } from '../../auth/hooks/useAuth';
import type { GlobeMethods } from 'react-globe.gl';
import { fetchMyProfile } from '../../profiles/api/profileApi';
import { fetchOnlineUsers, fetchUserProfile } from '../api/worldApi';

/**
 * Approximate bounding box visible from camera POV at given altitude.
 */
function getBoundingBox(lat: number, lng: number, altitude: number) {
  const latSpan = Math.min(180, altitude * 45);
  const lngSpan = Math.min(360, altitude * 65);
  return {
    minLat: Math.max(-90, lat - latSpan / 2),
    maxLat: Math.min(90, lat + latSpan / 2),
    minLng: Math.max(-180, lng - lngSpan / 2),
    maxLng: Math.min(180, lng + lngSpan / 2),
  };
}


// Welcome state from onboarding
type WelcomeState = {
  welcomeUser?: boolean;
  focusLat?: number;
  focusLng?: number;
  focusUsername?: string;
};

export default function JukeWorldRoute() {
  const { isAuthenticated, username, token } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [dimensions, setDimensions] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [selectedPoint, setSelectedPoint] = useState<GlobePoint | null>(null);
  const [welcomeMessage, setWelcomeMessage] = useState<string | null>(null);
  const [globeReady, setGlobeReady] = useState(false);
  const [initialDataLoaded, setInitialDataLoaded] = useState(false);
  const [selfPoint, setSelfPoint] = useState<GlobePoint | null>(null);
  const [showUserList, setShowUserList] = useState(false);
  const [onlineUsers, setOnlineUsers] = useState<GlobePoint[]>([]);
  const [onlineCount, setOnlineCount] = useState(0);
  const [onlineOffset, setOnlineOffset] = useState(0);
  const [onlineLoading, setOnlineLoading] = useState(false);
  const [hexUsers, setHexUsers] = useState<GlobePoint[]>([]);
  const [hexOpen, setHexOpen] = useState(false);
  const initialLoadDone = useRef(false);
  const welcomeHandled = useRef(false);
  const welcomeSelectionDone = useRef(false);
  const welcomeTargetRef = useRef<{ username?: string; lat?: number; lng?: number } | null>(null);
  const globeRef = useRef<GlobeMethods | null>(null);
  const lastCameraRef = useRef<{ lat: number; lng: number; altitude: number } | null>(null);
  const { points: apiPoints, loadPoints, loading: pointsLoading } = useGlobePoints(token);
  const { userDetail, loading: userLoading, loadUser, clearUser } = useUserDetail(token);

  // Handle window resize
  useEffect(() => {
    const handleResize = () => setDimensions({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      loadPoints({ min_lat: -90, max_lat: 90, min_lng: -180, max_lng: 180, zoom: 1 });
    }
  }, [loadPoints]);

  useEffect(() => {
    if (!pointsLoading && initialLoadDone.current) {
      setInitialDataLoaded(true);
    }
  }, [pointsLoading]);

  useEffect(() => {
    if (!token || !username) {
      setSelfPoint(null);
      return;
    }

    let active = true;
    const loadSelf = async () => {
      try {
        const profile = await fetchMyProfile(token);
        if (!active) return;
        if (typeof profile.city_lat !== 'number' || typeof profile.city_lng !== 'number') {
          return;
        }
        const clout = typeof profile.clout === 'number' ? profile.clout : 0.1;
        setSelfPoint({
          id: profile.id,
          username: profile.username,
          lat: profile.city_lat,
          lng: profile.city_lng,
          clout,
          top_genre: profile.top_genre ?? 'other',
          display_name: profile.display_name ?? profile.username,
          location: profile.location,
        });
      } catch {
        if (active) {
          setSelfPoint(null);
        }
      }
    };

    void loadSelf();
    return () => {
      active = false;
    };
  }, [token, username]);

  useEffect(() => {
    if (!token) {
      setOnlineUsers([]);
      setOnlineCount(0);
      return;
    }

    let active = true;
    const loadOnline = async () => {
      setOnlineLoading(true);
      try {
        const response = await fetchOnlineUsers(token, 10, onlineOffset);
        if (!active) return;
        if (Array.isArray(response)) {
          setOnlineUsers(
            response.map((profile) => ({
              id: profile.id,
              username: profile.username,
              lat: profile.city_lat ?? 0,
              lng: profile.city_lng ?? 0,
              clout: profile.clout ?? 0,
              top_genre: profile.top_genre ?? 'other',
              display_name: profile.display_name ?? profile.username,
              location: profile.location,
            })),
          );
          setOnlineCount(response.length);
        } else {
          setOnlineUsers(
            response.results.map((profile) => ({
              id: profile.id,
              username: profile.username,
              lat: profile.city_lat ?? 0,
              lng: profile.city_lng ?? 0,
              clout: profile.clout ?? 0,
              top_genre: profile.top_genre ?? 'other',
              display_name: profile.display_name ?? profile.username,
              location: profile.location,
            })),
          );
          setOnlineCount(response.count);
        }
      } catch {
        if (active) {
          setOnlineUsers([]);
          setOnlineCount(0);
        }
      } finally {
        if (active) {
          setOnlineLoading(false);
        }
      }
    };

    void loadOnline();
    return () => {
      active = false;
    };
  }, [token, onlineOffset]);

  const readWelcomeState = useCallback(() => {
    const state = location.state as WelcomeState | null;
    const params = new URLSearchParams(location.search);
    const welcomeFromQuery = params.get('welcome') === '1' || params.get('welcome') === 'true';
    const focusLat = params.get('focusLat');
    const focusLng = params.get('focusLng');
    const focusUsername = params.get('focusUsername');
    const parsedLat = focusLat ? Number(focusLat) : undefined;
    const parsedLng = focusLng ? Number(focusLng) : undefined;

    return {
      welcomeUser: state?.welcomeUser || welcomeFromQuery,
      focusLat: state?.focusLat ?? (Number.isFinite(parsedLat) ? parsedLat : undefined),
      focusLng: state?.focusLng ?? (Number.isFinite(parsedLng) ? parsedLng : undefined),
      focusUsername: state?.focusUsername ?? focusUsername ?? undefined,
    } satisfies WelcomeState;
  }, [location.search, location.state]);

  // Handle welcome user from onboarding (state or query params)
  useEffect(() => {
    const state = readWelcomeState();
    if (state?.welcomeUser && !welcomeHandled.current) {
      welcomeHandled.current = true;
      if (state.focusLat != null && state.focusLng != null) {
        welcomeTargetRef.current = {
          username: state.focusUsername || username || undefined,
          lat: state.focusLat,
          lng: state.focusLng,
        };
      }

      const showTimer = setTimeout(() => {
        setWelcomeMessage("Welcome to Juke World! You're now on the map.");
      }, 0);
      const hideTimer = setTimeout(() => setWelcomeMessage(null), 5000);

      // Zoom to user's location if available
      if (state.focusLat != null && state.focusLng != null && globeRef.current) {
        // Delay slightly to let globe initialize
        setTimeout(() => {
          globeRef.current?.pointOfView(
            { lat: state.focusLat!, lng: state.focusLng!, altitude: 0.38 },
            1400
          );
        }, 200);
      }

      if (state.focusLat != null && state.focusLng != null) {
        const bbox = getBoundingBox(state.focusLat, state.focusLng, 0.38);
        loadPoints({
          min_lat: bbox.minLat,
          max_lat: bbox.maxLat,
          min_lng: bbox.minLng,
          max_lng: bbox.maxLng,
          zoom: 12,
          limit: 5000,
        });
      }

      // Clear location state + query params to prevent re-triggering
      window.history.replaceState({}, document.title, window.location.pathname);

      return () => {
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
      };
    }
  }, [readWelcomeState, username, loadPoints]);

  useEffect(() => {
    const target = welcomeTargetRef.current;
    if (!target || welcomeSelectionDone.current) {
      return;
    }
    const targetUsername = target.username;
    if (!targetUsername) {
      return;
    }

    const matchedPoint = apiPoints.find((point) => point.username === targetUsername);

    if (matchedPoint) {
      welcomeSelectionDone.current = true;
      const timer = setTimeout(() => {
        setSelectedPoint(matchedPoint);
        if (globeRef.current) {
          globeRef.current.pointOfView(
            { lat: matchedPoint.lat, lng: matchedPoint.lng, altitude: 0.38 },
            1200,
          );
        }
        loadUser(targetUsername);
      }, 0);
      return () => clearTimeout(timer);
    }

    if (target.lat != null && target.lng != null) {
      const fallbackPoint = {
        id: -1,
        username: targetUsername,
        lat: target.lat,
        lng: target.lng,
        clout: 0.2,
        top_genre: 'other',
        display_name: targetUsername,
      };
      welcomeSelectionDone.current = true;
      const timer = setTimeout(() => {
        setSelectedPoint(fallbackPoint);
        if (globeRef.current) {
          globeRef.current.pointOfView(
            { lat: fallbackPoint.lat, lng: fallbackPoint.lng, altitude: 0.38 },
            1200,
          );
        }
        loadUser(targetUsername);
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [apiPoints, loadUser]);

  // Camera change handler — triggers LOD re-filter
  const handleCameraChange = useCallback(
    (pov: { lat: number; lng: number; altitude: number }) => {
      const last = lastCameraRef.current;
      if (last) {
        const latDelta = Math.abs(pov.lat - last.lat);
        const lngDelta = Math.abs(pov.lng - last.lng);
        const altDelta = Math.abs(pov.altitude - last.altitude);
        if (latDelta < 0.3 && lngDelta < 0.3 && altDelta < 0.05) {
          return;
        }
      }
      lastCameraRef.current = pov;
      const zoom = Math.max(1, Math.min(20, Math.round(20 - pov.altitude * 5)));
      const latSpan = Math.min(180, pov.altitude * 40);
      const lngSpan = Math.min(360, pov.altitude * 60);
      loadPoints({
        min_lat: Math.max(-90, pov.lat - latSpan / 2),
        max_lat: Math.min(90, pov.lat + latSpan / 2),
        min_lng: Math.max(-180, pov.lng - lngSpan / 2),
        max_lng: Math.min(180, pov.lng + lngSpan / 2),
        zoom,
      });
    },
    [loadPoints],
  );

  const points = useMemo(() => {
    if (!selfPoint) return apiPoints;
    const hasSelf = apiPoints.some((point) => point.username === selfPoint.username);
    if (hasSelf) return apiPoints;
    return [selfPoint, ...apiPoints];
  }, [apiPoints, selfPoint]);

  const focusPoint = useCallback((point: GlobePoint) => {
    if (globeRef.current) {
      globeRef.current.pointOfView(
        { lat: point.lat, lng: point.lng, altitude: 0.55 },
        1200,
      );
    }
  }, []);

  const focusUserByUsername = useCallback(
    async (user: GlobePoint) => {
      const point = points.find((candidate) => candidate.username === user.username);
      if (point) {
        focusPoint(point);
        return;
      }
      if (!token) return;
      try {
        const profile = await fetchUserProfile(user.username, token);
        if (typeof profile.city_lat !== 'number' || typeof profile.city_lng !== 'number') {
          return;
        }
        focusPoint({
          id: profile.id,
          username: profile.username,
          lat: profile.city_lat,
          lng: profile.city_lng,
          clout: profile.clout ?? 0.1,
          top_genre: profile.top_genre ?? 'other',
          display_name: profile.display_name ?? profile.username,
          location: profile.location,
        });
      } catch {
        // Ignore failures; still show the modal if available.
      }
    },
    [focusPoint, points, token],
  );

  const handleHexClick = useCallback((hex: unknown) => {
    const pointsInHex = (hex as { points?: GlobePoint[] }).points ?? [];
    setHexUsers(pointsInHex.slice(0, 40));
    setHexOpen(true);
  }, []);

  const handleHexHover = useCallback(() => {}, []);


  // Handle point click
  const handlePointClick = useCallback(
    (point: GlobePoint) => {
      setSelectedPoint(point);
      loadUser(point.username);
      focusPoint(point);
    },
    [loadUser, focusPoint],
  );

  const handleCloseModal = useCallback(() => {
    setSelectedPoint(null);
    clearUser();
  }, [clearUser]);

  const displayUser = userDetail;

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        position: 'relative',
        background: '#050510',
      }}
    >
      {/* Globe */}
      <div style={{ position: 'absolute', inset: 0, touchAction: 'none' }}>
        <JukeGlobe
          points={points}
          width={dimensions.width}
          height={dimensions.height}
          globeRef={globeRef}
          onPointClick={handlePointClick}
          onCameraChange={handleCameraChange}
          onHexClick={handleHexClick}
          onHexHover={handleHexHover}
          onGlobeReady={() => setGlobeReady(true)}
        />
      </div>

      {/* Overlay navigation */}
      <GlobeOverlayNav />

      {/* Welcome message toast */}
      {welcomeMessage && (
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'rgba(0,0,0,0.9)',
            backdropFilter: 'blur(16px)',
            borderRadius: 16,
            padding: '32px 48px',
            zIndex: 100,
            textAlign: 'center',
            border: '1px solid rgba(249, 115, 22, 0.3)',
            boxShadow: '0 0 60px rgba(249, 115, 22, 0.2)',
            animation: 'welcomeFadeIn 0.5s ease',
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 16 }}>🎉</div>
          <h2 style={{
            fontSize: 24,
            fontWeight: 700,
            color: '#fff',
            margin: '0 0 8px',
            fontFamily: 'Space Grotesk, sans-serif'
          }}>
            {welcomeMessage}
          </h2>
          <p style={{
            fontSize: 14,
            color: 'rgba(255,255,255,0.6)',
            margin: 0,
            fontFamily: 'Space Grotesk, sans-serif'
          }}>
            Explore the global community of music lovers
          </p>
        </div>
      )}

      {/* User detail modal */}
      {selectedPoint && (
        <UserDetailModal
          user={displayUser}
          loading={userLoading}
          clout={selectedPoint.clout}
          topGenre={selectedPoint.top_genre}
          onClose={handleCloseModal}
        />
      )}


      {/* Point count HUD */}
      <button
        type="button"
        onClick={() => setShowUserList((prev) => !prev)}
        style={{
          position: 'absolute',
          top: 70,
          left: 24,
          background: 'rgba(0,0,0,0.65)',
          backdropFilter: 'blur(8px)',
          borderRadius: 999,
          padding: '8px 16px',
          zIndex: 10,
          fontFamily: 'system-ui, -apple-system, sans-serif',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          cursor: 'pointer',
          border: '1px solid rgba(255,255,255,0.15)',
          color: '#fff',
        }}
        aria-expanded={showUserList}
      >
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: '#00e5ff',
            boxShadow: '0 0 8px #00e5ff',
            animation: 'pulse 2s ease-in-out infinite',
          }}
        />
        <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.85)', fontWeight: 600 }}>
          {onlineCount.toLocaleString()} users online
        </span>
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>▼</span>
      </button>

      {showUserList && (
        <div
          style={{
            position: 'absolute',
            top: 112,
            left: 24,
            width: 320,
            maxHeight: 360,
            overflowY: 'auto',
            background: 'rgba(0,0,0,0.85)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 10,
            padding: 8,
            zIndex: 11,
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {onlineLoading ? (
            <div style={{ padding: '12px 10px', fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>
              Loading online users...
            </div>
          ) : null}
          {!onlineLoading && onlineUsers.length === 0 ? (
            <div style={{ padding: '12px 10px', fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>
              No online users right now.
            </div>
          ) : null}
          {onlineUsers.map((point) => (
            <button
              key={point.username}
              onClick={() => {
                handlePointClick(point);
                void focusUserByUsername(point);
                setShowUserList(false);
              }}
              style={{
                width: '100%',
                textAlign: 'left',
                background: 'transparent',
                border: 'none',
                padding: '8px 10px',
                color: '#fff',
                cursor: 'pointer',
                borderRadius: 6,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.08)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                {point.display_name || point.username}
              </div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)' }}>
                @{point.username} • {point.location ?? `${point.lat.toFixed(2)}, ${point.lng.toFixed(2)}`}
              </div>
            </button>
          ))}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              padding: '8px 6px 4px',
              gap: 8,
            }}
          >
            <button
              type="button"
              onClick={() => setOnlineOffset((prev) => Math.max(0, prev - 10))}
              disabled={onlineOffset === 0}
              style={{
                flex: 1,
                background: 'rgba(255,255,255,0.08)',
                border: '1px solid rgba(255,255,255,0.12)',
                color: '#fff',
                borderRadius: 8,
                padding: '6px 8px',
                cursor: onlineOffset === 0 ? 'not-allowed' : 'pointer',
                opacity: onlineOffset === 0 ? 0.5 : 1,
                fontSize: 12,
              }}
            >
              Prev
            </button>
            <button
              type="button"
              onClick={() => {
                const nextOffset = onlineOffset + 10;
                if (nextOffset < onlineCount) setOnlineOffset(nextOffset);
              }}
              disabled={onlineOffset + 10 >= onlineCount}
              style={{
                flex: 1,
                background: 'rgba(255,255,255,0.08)',
                border: '1px solid rgba(255,255,255,0.12)',
                color: '#fff',
                borderRadius: 8,
                padding: '6px 8px',
                cursor: onlineOffset + 10 >= onlineCount ? 'not-allowed' : 'pointer',
                opacity: onlineOffset + 10 >= onlineCount ? 0.5 : 1,
                fontSize: 12,
              }}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {hexOpen && (
        <div
          style={{
            position: 'absolute',
            top: 120,
            left: 24,
            width: 320,
            maxHeight: 360,
            overflowY: 'auto',
            background: 'rgba(5,5,15,0.92)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 12,
            padding: 10,
            zIndex: 12,
            fontFamily: 'system-ui, -apple-system, sans-serif',
            boxShadow: '0 12px 30px rgba(0,0,0,0.35)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)', letterSpacing: '0.4px' }}>
              USERS IN HEX
            </div>
            <button
              onClick={() => setHexOpen(false)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'rgba(255,255,255,0.6)',
                cursor: 'pointer',
                fontSize: 16,
              }}
            >
              ×
            </button>
          </div>
          {hexUsers.length === 0 ? (
            <div style={{ padding: '8px 4px', fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>
              No users in this area.
            </div>
          ) : null}
          {hexUsers.map((point) => (
            <button
              key={`hex-${point.username}`}
              onClick={() => {
                handlePointClick(point);
                void focusUserByUsername(point);
              }}
              style={{
                width: '100%',
                textAlign: 'left',
                background: 'transparent',
                border: 'none',
                padding: '8px 10px',
                color: '#fff',
                cursor: 'pointer',
                borderRadius: 6,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.08)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                {point.display_name || point.username}
              </div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)' }}>
                @{point.username} • {point.location ?? `${point.lat.toFixed(2)}, ${point.lng.toFixed(2)}`}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Loading veil */}
      {!globeReady || !initialDataLoaded ? (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'radial-gradient(circle at top, rgba(5,10,30,0.9), rgba(2,2,10,0.98))',
            zIndex: 4,
            color: '#fff',
            fontFamily: 'Space Grotesk, sans-serif',
            letterSpacing: '0.3px',
          }}
        >
          Loading Juke World...
        </div>
      ) : null}

      {/* Genre legend */}
      <div
        style={{
          position: 'absolute',
          bottom: 24,
          left: 24,
          background: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(12px)',
          borderRadius: 10,
          padding: '12px 16px',
          zIndex: 10,
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
      >
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 8, letterSpacing: '0.5px' }}>
          GENRES
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {[
            { genre: 'Pop', color: '#FF6B9D' },
            { genre: 'Rock', color: '#E74C3C' },
            { genre: 'Country', color: '#F39C12' },
            { genre: 'Rap', color: '#9B59B6' },
            { genre: 'Folk', color: '#27AE60' },
            { genre: 'Jazz', color: '#3498DB' },
            { genre: 'Classical', color: '#1ABC9C' },
          ].map(({ genre, color }) => (
            <div key={genre} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }}>{genre}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Animation keyframes */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }
        @keyframes welcomeFadeIn {
          from {
            opacity: 0;
            transform: translate(-50%, -50%) scale(0.9);
          }
          to {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
          }
        }
      `}</style>
    </div>
  );
}
