import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import JukeGlobe from '../components/JukeGlobe';
import GlobeOverlayNav from '../components/GlobeOverlayNav';
import UserDetailModal from '../components/UserDetailModal';
import { useGlobePoints } from '../hooks/useGlobePoints';
import { useUserDetail } from '../hooks/useUserDetail';
import { generateMockPoints } from '../mockData';
import { GlobePoint } from '../types';
import { useAuth } from '../../auth/hooks/useAuth';

// Use mock data when API is unavailable (dev without backend)
const USE_MOCK = true;
const MOCK_TOTAL = 50000;
const MAX_VISIBLE_POINTS = 8000;

/**
 * Client-side LOD: given camera altitude, return a clout threshold.
 * Lower altitude (more zoomed in) → lower threshold → more points visible.
 */
function getCloutThreshold(altitude: number): number {
  if (altitude > 2.0) return 0.5;      // Globe view: only top users
  if (altitude > 1.2) return 0.25;     // Continent level
  if (altitude > 0.7) return 0.1;      // Country level
  if (altitude > 0.4) return 0.03;     // Region level
  return 0.0;                           // City level: show everyone
}

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

/**
 * Filter points by bounding box and clout threshold.
 */
function filterPoints(
  allPoints: GlobePoint[],
  lat: number,
  lng: number,
  altitude: number,
): GlobePoint[] {
  const threshold = getCloutThreshold(altitude);
  const bbox = getBoundingBox(lat, lng, altitude);

  // At very high altitude, skip bbox (entire globe is visible)
  const useBbox = altitude < 2.5;

  const filtered: GlobePoint[] = [];
  for (const p of allPoints) {
    if (p.clout < threshold) continue;
    if (useBbox) {
      if (p.lat < bbox.minLat || p.lat > bbox.maxLat) continue;
      if (p.lng < bbox.minLng || p.lng > bbox.maxLng) continue;
    }
    filtered.push(p);
    if (filtered.length >= MAX_VISIBLE_POINTS) break;
  }
  return filtered;
}

export default function JukeWorldRoute() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [dimensions, setDimensions] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [selectedPoint, setSelectedPoint] = useState<GlobePoint | null>(null);
  const initialLoadDone = useRef(false);

  // Full dataset (sorted by clout DESC for efficient LOD filtering)
  const allMockPoints = useMemo(() => {
    if (!USE_MOCK) return [];
    const pts = generateMockPoints(MOCK_TOTAL);
    pts.sort((a, b) => b.clout - a.clout);
    return pts;
  }, []);

  const initialVisiblePoints = useMemo(() => {
    if (!USE_MOCK || allMockPoints.length === 0) return [];
    return filterPoints(allMockPoints, 20, 0, 2.5);
  }, [allMockPoints]);

  const [visiblePoints, setVisiblePoints] = useState<GlobePoint[]>(initialVisiblePoints);

  // Auth token from localStorage (matches existing auth pattern)
  const token = useMemo(() => localStorage.getItem('token'), []);

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

  // Initial load: show high-clout global view
  useEffect(() => {
    if (!USE_MOCK && !initialLoadDone.current) {
      initialLoadDone.current = true;
      loadPoints({ min_lat: -90, max_lat: 90, min_lng: -180, max_lng: 180, zoom: 1 });
    }
  }, [loadPoints]);

  // Camera change handler — triggers LOD re-filter
  const handleCameraChange = useCallback(
    (pov: { lat: number; lng: number; altitude: number }) => {
      if (USE_MOCK) {
        const filtered = filterPoints(allMockPoints, pov.lat, pov.lng, pov.altitude);
        setVisiblePoints(filtered);
      } else {
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
      }
    },
    [allMockPoints, loadPoints],
  );

  const points = USE_MOCK ? visiblePoints : apiPoints;

  // Handle point click
  const handlePointClick = useCallback(
    (point: GlobePoint) => {
      setSelectedPoint(point);
      if (!USE_MOCK) {
        loadUser(point.username);
      }
    },
    [loadUser],
  );

  const handleCloseModal = useCallback(() => {
    setSelectedPoint(null);
    clearUser();
  }, [clearUser]);

  // Build mock user detail from the selected point
  const mockUserDetail = useMemo(() => {
    if (!selectedPoint || !USE_MOCK) return null;
    return {
      id: selectedPoint.id,
      username: selectedPoint.username,
      name: null,
      display_name: selectedPoint.display_name,
      tagline: `${selectedPoint.top_genre.charAt(0).toUpperCase() + selectedPoint.top_genre.slice(1)} enthusiast`,
      bio: '',
      location: `${selectedPoint.lat.toFixed(2)}, ${selectedPoint.lng.toFixed(2)}`,
      avatar_url: '',
      favorite_genres: [selectedPoint.top_genre, 'rock', 'jazz'],
      favorite_artists: ['Artist One', 'Artist Two', 'Artist Three'],
      favorite_albums: [],
      favorite_tracks: [],
      created_at: '',
      modified_at: '',
      is_owner: false,
    };
  }, [selectedPoint]);

  const displayUser = USE_MOCK ? mockUserDetail : userDetail;

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
          onPointClick={handlePointClick}
          onCameraChange={handleCameraChange}
        />
      </div>

      {/* Overlay navigation */}
      <GlobeOverlayNav />

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
          / {USE_MOCK ? MOCK_TOTAL.toLocaleString() : '—'} total
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

      {/* Pulse animation keyframes */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }
      `}</style>
    </div>
  );
}
