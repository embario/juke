import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import JukeGlobe from '../components/JukeGlobe';
import GlobeOverlayNav from '../components/GlobeOverlayNav';
import UserDetailModal from '../components/UserDetailModal';
import { useGlobePoints } from '../hooks/useGlobePoints';
import { useUserDetail } from '../hooks/useUserDetail';
import { GlobePoint } from '../types';
import { useAuth } from '../../auth/hooks/useAuth';
import type { GlobeMethods } from 'react-globe.gl';

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
  const initialLoadDone = useRef(false);
  const welcomeHandled = useRef(false);
  const welcomeSelectionDone = useRef(false);
  const welcomeTargetRef = useRef<{ username?: string; lat?: number; lng?: number } | null>(null);
  const globeRef = useRef<GlobeMethods | null>(null);
  const { points: apiPoints, loadPoints } = useGlobePoints(token);
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

  // Handle welcome user from onboarding
  useEffect(() => {
    const state = location.state as WelcomeState | null;
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

      // Clear location state to prevent re-triggering
      window.history.replaceState({}, document.title);

      return () => {
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
      };
    }
  }, [location.state, username, loadPoints]);

  useEffect(() => {
    const target = welcomeTargetRef.current;
    if (!target || welcomeSelectionDone.current) {
      return;
    }
    if (!target.username) {
      return;
    }

    const matchedPoint = apiPoints.find((point) => point.username === target.username);

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
        loadUser(target.username);
      }, 0);
      return () => clearTimeout(timer);
    }

    if (target.lat != null && target.lng != null) {
      const fallbackPoint = {
        id: -1,
        username: target.username,
        lat: target.lat,
        lng: target.lng,
        clout: 0.2,
        top_genre: 'other',
        display_name: target.username,
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
        loadUser(target.username);
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [apiPoints, loadUser]);

  // Camera change handler — triggers LOD re-filter
  const handleCameraChange = useCallback(
    (pov: { lat: number; lng: number; altitude: number }) => {
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

  const points = apiPoints;

  // Handle point click
  const handlePointClick = useCallback(
    (point: GlobePoint) => {
      setSelectedPoint(point);
      loadUser(point.username);
    },
    [loadUser],
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
      <div style={{ position: 'absolute', inset: 0 }}>
        <JukeGlobe
          points={points}
          width={dimensions.width}
          height={dimensions.height}
          globeRef={globeRef}
          onPointClick={handlePointClick}
          onCameraChange={handleCameraChange}
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
      <div
        style={{
          position: 'absolute',
          top: 70,
          left: 24,
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(8px)',
          borderRadius: 8,
          padding: '8px 14px',
          zIndex: 10,
          fontFamily: 'system-ui, -apple-system, sans-serif',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: '#00e5ff',
            boxShadow: '0 0 6px #00e5ff',
            animation: 'pulse 2s ease-in-out infinite',
          }}
        />
        <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.8)', fontWeight: 500 }}>
          {points.length.toLocaleString()} users visible
        </span>
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>
          / — total
        </span>
      </div>

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
